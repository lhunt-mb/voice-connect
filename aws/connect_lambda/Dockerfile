# Dockerfile for packaging Lambda function
FROM public.ecr.aws/lambda/python:3.12

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements.txt

# Copy handler and ensure it has correct permissions
COPY handler.py ${LAMBDA_TASK_ROOT}/
RUN chmod 644 ${LAMBDA_TASK_ROOT}/handler.py

# Set the CMD to your handler
CMD ["handler.lambda_handler"]
