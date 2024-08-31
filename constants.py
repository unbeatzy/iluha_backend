from dotenv import load_dotenv
import os

load_dotenv()

API_TOKEN = os.getenv('API_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')
YOOMONEY_TOKEN = os.getenv('YOOMONEY_TOKEN')
YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET')
DB_NAME = os.getenv('DB_NAME')

WEBHOOK_PATH = os.getenv('WEBHOOK_PATH')
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST')
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBHOOK_SSL_CERT = os.getenv('WEBHOOK_SSL_CERT')
WEBHOOK_SSL_PRIV = os.getenv('WEBHOOK_SSL_PRIV')

WEBAPP_HOST = os.getenv('WEBAPP_HOST')
WEBAPP_PORT = int(os.getenv('WEBAPP_PORT'))