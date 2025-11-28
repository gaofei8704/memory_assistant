from datetime import datetime, timedelta
from models import ContentStatus,Content


def create_content_status(content_id):
    """创建内容学习状态记录"""
    status = ContentStatus(
        content_id=content_id,
        status='new',
        memory_strength=0.0,
        interval=0,
        review_count=0,
        correct_count=0,
        total_time=0,
        last_reviewed=None,
        next_review=None
    )
    return status

# 在 utils.py 中添加带进度的内容选择函数
def select_study_content_with_progress(deck_id, daily_goal, start_index=0):
    """
    选择学习内容，包括新内容和到期的复习内容
    """
    # 获取到期需要复习的内容
    due_reviews = ContentStatus.query.join(Content).filter(
        Content.deck_id == deck_id,
        ContentStatus.next_review <= datetime.now(),
        ContentStatus.status != 'too_easy',
        ContentStatus.status != 'mastered'
    ).order_by(ContentStatus.memory_strength.asc()).all()

    # 获取新内容
    learned_content_ids = [status.content_id for status in due_reviews]
    new_contents = Content.query.filter(
        Content.deck_id == deck_id,
        ~Content.id.in_(learned_content_ids)
    ).limit(daily_goal).all()

    # 组合内容：先复习到期内容，再添加新内容
    study_content = []

    # 添加到期复习内容
    for status in due_reviews:
        study_content.append(('review', status.content))

    # 添加新内容
    for content in new_contents:
        study_content.append(('new', content))

    # 限制总数
    end_index = start_index + daily_goal
    study_content = study_content[start_index:end_index]

    return study_content



# 简单的算法函数（后续会完善）
def get_due_review_items(deck_id, limit=20):
    """获取到期复习的内容（简单版本）"""
    from models import db, Content, ContentStatus

    due_items = ContentStatus.query.join(Content).filter(
        Content.deck_id == deck_id,
        ContentStatus.next_review <= datetime.now(),
        ContentStatus.status != 'too_easy'
    ).order_by(
        ContentStatus.next_review.asc()
    ).limit(limit).all()

    return [status.content for status in due_items]


def get_new_items(deck_id, limit=10):
    """获取新内容（简单版本）"""
    from models import db, Content, ContentStatus

    # 找到已经有状态记录的内容ID
    learned_content_ids = db.session.query(ContentStatus.content_id).subquery()

    new_contents = Content.query.filter(
        Content.deck_id == deck_id,
        ~Content.id.in_(learned_content_ids)
    ).limit(limit).all()

    return new_contents


def mix_content(review_items, new_items):
    """混合新旧内容"""
    mixed = []
    max_len = max(len(review_items), len(new_items))

    for i in range(max_len):
        if i < len(review_items):
            mixed.append(('review', review_items[i]))
        if i < len(new_items):
            mixed.append(('new', new_items[i]))

    return mixed


def select_study_content(deck_id, daily_goal):
    """根据学习策略选择内容"""
    # 优先选择待复习内容
    due_review = ContentStatus.query.join(Content).filter(
        Content.deck_id == deck_id,
        ContentStatus.next_review <= datetime.now(),
        ContentStatus.status != 'too_easy'
    ).all()

    # 选择新内容补充
    learned_content_ids = [status.content_id for status in due_review]
    new_content = Content.query.filter(
        Content.deck_id == deck_id,
        ~Content.id.in_(learned_content_ids)
    ).limit(daily_goal - len(due_review)).all()

    # 组合结果
    study_content = [('review', status.content) for status in due_review]
    study_content.extend([('new', content) for content in new_content])

    return study_content[:daily_goal]


def calculate_next_review_interval(review_count, ease_factor, quality):
    """
    根据艾宾浩斯记忆曲线计算下次复习间隔
    review_count: 复习次数
    ease_factor: 掌握程度因子
    quality: 回答质量 (0-5)
    """
    if quality < 3:  # 回答错误
        return 1  # 1天后复习

    if review_count == 0:
        return 1  # 第一次学习，1天后复习
    elif review_count == 1:
        return 3  # 3天后复习
    elif review_count == 2:
        return 7  # 7天后复习
    elif review_count == 3:
        return 14  # 14天后复习
    else:
        # 使用间隔重复算法
        interval = 14 * (ease_factor ** (review_count - 3))
        return max(14, int(interval))

def update_content_status_based_on_ebbinghaus(status, quality, response_time):
    """
    根据艾宾浩斯记忆曲线更新内容状态
    """
    status.review_count += 1
    status.total_time += response_time

    if quality >= 3:  # 正确回答
        status.correct_count += 1
        status.memory_strength = min(1.0, status.memory_strength + 0.1 * quality)
    else:  # 错误回答
        status.correct_count = 0
        status.memory_strength = max(0.0, status.memory_strength - 0.2)

    # 计算掌握程度因子
    if status.ease_factor is None:
        status.ease_factor = 2.5

    if quality < 4:
        status.ease_factor = max(1.3, status.ease_factor - 0.2)
    elif quality > 4:
        status.ease_factor = min(3.0, status.ease_factor + 0.1)

    # 计算下次复习时间
    next_interval = calculate_next_review_interval(
        status.review_count,
        status.ease_factor,
        quality
    )

    status.interval = next_interval
    status.next_review = datetime.now() + timedelta(days=next_interval)

    # 更新状态
    if status.memory_strength >= 0.9 and status.review_count >= 5:
        status.status = 'mastered'
    elif status.memory_strength >= 0.7:
        status.status = 'too_easy'
    else:
        status.status = 'learning'
