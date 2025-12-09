import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()


class Config:
    """基础配置类"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')

    # MySQL数据库配置
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'GaoFei!@#4')
    MYSQL_DB = os.getenv('MYSQL_DB', 'memory_assistant')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
    encoded_password = quote_plus(MYSQL_PASSWORD)
    # SQLAlchemy配置
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # 设置为True可以查看SQL语句


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False


# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}