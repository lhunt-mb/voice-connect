# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  configuration {
    execute_command_configuration {
      logging = "OVERRIDE"

      log_configuration {
        cloud_watch_log_group_name = aws_cloudwatch_log_group.ecs_exec.name
      }
    }
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "ecs_exec" {
  name              = "/aws/ecs/${local.name_prefix}-exec"
  retention_in_days = 7
  kms_key_id        = aws_kms_key.logs.arn

  tags = local.common_tags
}

# CloudWatch Log Group for Gateway Service
resource "aws_cloudwatch_log_group" "gateway" {
  name              = local.gateway_log_group
  retention_in_days = var.environment == "prod" ? 90 : 30
  kms_key_id        = aws_kms_key.logs.arn

  tags = local.common_tags
}

# ECS Task Definition for Gateway Service
resource "aws_ecs_task_definition" "gateway" {
  family                   = local.gateway_service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.gateway_cpu
  memory                   = var.gateway_memory_mib
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "gateway"
      image     = "${aws_ecr_repository.gateway.repository_url}:${var.gateway_image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "NOVA_REGION"
          value = var.nova_region
        },
        {
          name  = "DYNAMODB_TABLE_NAME"
          value = local.dynamodb_table_name
        },
        {
          name  = "LOG_LEVEL"
          value = var.log_level
        },
        {
          name  = "PUBLIC_HOST"
          value = var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name
        }
      ]

      secrets = [
        {
          name      = "TWILIO_ACCOUNT_SID"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:TWILIO_ACCOUNT_SID::"
        },
        {
          name      = "TWILIO_AUTH_TOKEN"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:TWILIO_AUTH_TOKEN::"
        },
        {
          name      = "TWILIO_PHONE_NUMBER"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:TWILIO_PHONE_NUMBER::"
        },
        {
          name      = "VOICE_PROVIDER"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:VOICE_PROVIDER::"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_API_KEY::"
        },
        {
          name      = "OPENAI_REALTIME_MODEL"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_REALTIME_MODEL::"
        },
        {
          name      = "OPENAI_VOICE"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_VOICE::"
        },
        {
          name      = "CONNECT_PHONE_NUMBER"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:CONNECT_PHONE_NUMBER::"
        },
        {
          name      = "CONNECT_INSTANCE_ID"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:CONNECT_INSTANCE_ID::"
        },
        {
          name      = "HUBSPOT_ACCESS_TOKEN"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:HUBSPOT_ACCESS_TOKEN::"
        },
        {
          name      = "ENABLE_HUBSPOT"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:ENABLE_HUBSPOT::"
        },
        {
          name      = "TOKEN_TTL_SECONDS"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:TOKEN_TTL_SECONDS::"
        },
        {
          name      = "TOKEN_LENGTH"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:TOKEN_LENGTH::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = local.gateway_log_group
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "gateway"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  tags = local.common_tags
}

# ECS Service for Gateway
resource "aws_ecs_service" "gateway" {
  name            = local.gateway_service_name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.gateway.arn
  desired_count   = var.gateway_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.gateway.arn
    container_name   = "gateway"
    container_port   = 8000
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = true

  tags = local.common_tags

  depends_on = [
    aws_lb_listener.http,
    aws_lb_listener.https
  ]

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# Auto Scaling for ECS Service
resource "aws_appautoscaling_target" "gateway" {
  max_capacity       = var.gateway_max_capacity
  min_capacity       = var.gateway_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.gateway.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Auto Scaling Policy - CPU
resource "aws_appautoscaling_policy" "gateway_cpu" {
  name               = "${local.gateway_service_name}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.gateway.resource_id
  scalable_dimension = aws_appautoscaling_target.gateway.scalable_dimension
  service_namespace  = aws_appautoscaling_target.gateway.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Auto Scaling Policy - Memory
resource "aws_appautoscaling_policy" "gateway_memory" {
  name               = "${local.gateway_service_name}-memory"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.gateway.resource_id
  scalable_dimension = aws_appautoscaling_target.gateway.scalable_dimension
  service_namespace  = aws_appautoscaling_target.gateway.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Auto Scaling Policy - ALB Request Count
resource "aws_appautoscaling_policy" "gateway_alb" {
  name               = "${local.gateway_service_name}-alb"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.gateway.resource_id
  scalable_dimension = aws_appautoscaling_target.gateway.scalable_dimension
  service_namespace  = aws_appautoscaling_target.gateway.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.gateway.arn_suffix}"
    }
    target_value       = 1000.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
