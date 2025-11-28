from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Deck(db.Model):
    """学习库模型"""
    __tablename__ = 'decks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 关系 - 设置级联删除
    contents = db.relationship('Content', backref='deck', lazy=True, cascade='all, delete-orphan')
    study_sessions = db.relationship('StudySession', backref='deck', lazy=True, cascade='all, delete-orphan')


class Content(db.Model):
    """学习内容模型"""
    __tablename__ = 'content'

    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('decks.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    front = db.Column(db.String(500), nullable=False)
    back = db.Column(db.String(500), nullable=False)
    example = db.Column(db.String(1000))
    unit = db.Column(db.String(20))  # 新增单元字段
    page = db.Column(db.String(20))  # 新增页码字段
    order = db.Column(db.Integer)  # 新增排序字段

    created_at = db.Column(db.DateTime, default=datetime.now)

    # 关系 - 设置级联删除
    status = db.relationship('ContentStatus', backref='content', uselist=False, cascade='all, delete-orphan')

    # 在 models.py 的 Content 类中添加或更新 to_dict 方法
    def to_dict(self):
        return {
            'id': self.id,
            'deck_id': self.deck_id,
            'type': self.type,
            'front': self.front,
            'back': self.back,
            'example': self.example,
            'unit': self.unit,  # 新增字段
            'page': self.page,  # 新增字段
            'order': self.order,  # 新增字段
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ContentStatus(db.Model):
    """内容学习状态模型"""
    __tablename__ = 'content_status'

    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('content.id', ondelete='CASCADE'), nullable=False)

    # 学习状态
    status = db.Column(db.String(20), default='new')
    memory_strength = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)

    # 时间相关
    last_reviewed = db.Column(db.DateTime)
    next_review = db.Column(db.DateTime)
    interval = db.Column(db.Integer, default=0)

    # 难度评估
    ease_factor = db.Column(db.Float, default=2.5)
    total_time = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


# 在 models.py 中更新 StudySession 类
class StudySession(db.Model):
    """学习会话模型"""
    __tablename__ = 'study_session'

    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('decks.id', ondelete='CASCADE'), nullable=False)
    duration = db.Column(db.Integer, default=0)
    total_items = db.Column(db.Integer, default=0)
    new_items = db.Column(db.Integer, default=0)
    reviewed_items = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    ended_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 新增字段用于记录学习进度
    current_index = db.Column(db.Integer, default=0)  # 当前学习位置
    completed = db.Column(db.Boolean, default=False)  # 是否已完成


# 在 models.py 中添加新的模型
class StudyConfig(db.Model):
    """学习配置模型"""
    __tablename__ = 'study_config'

    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('decks.id'), nullable=False)
    mode = db.Column(db.String(20), default='en_to_zh')  # 学习模式
    daily_goal = db.Column(db.Integer, default=20)
    study_order = db.Column(db.String(20), default='zh_first')
    is_configured = db.Column(db.Boolean, default=False)  # 是否已配置
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    deck = db.relationship('Deck', backref=db.backref('study_config', uselist=False))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class StudyBatch(db.Model):
    """学习批次"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deck_id = db.Column(db.Integer, db.ForeignKey('decks.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime)
    is_completed = db.Column(db.Boolean, default=False)
    current_index = db.Column(db.Integer, default=0)
    total_duration = db.Column(db.Integer, default=0)  # 总学习时长（秒）

    # 关联关系
    user = db.relationship('User', backref=db.backref('study_batches', lazy=True))
    deck = db.relationship('Deck', backref=db.backref('study_batches', lazy=True))


class StudyRecord(db.Model):
    """学习记录详情"""
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('study_batch.id'), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'), nullable=False)
    studied_at = db.Column(db.DateTime, default=datetime.now)
    response_time = db.Column(db.Integer)  # 回答用时（秒）
    user_input = db.Column(db.Text)  # 用户输入
    feedback_type = db.Column(db.String(20))  # too_easy, remembered, forgotten
    is_correct = db.Column(db.Boolean)  # 是否正确

    # 关联关系
    batch = db.relationship('StudyBatch', backref=db.backref('records', lazy=True))
    content = db.relationship('Content', backref=db.backref('study_records', lazy=True))
