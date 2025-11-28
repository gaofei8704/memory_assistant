import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from models import *
from config import config
from utils import create_content_status, select_study_content, select_study_content_with_progress
from datetime import datetime, timedelta
from functools import wraps


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # 初始化扩展
    db.init_app(app)

    # 注册模板过滤器
    @app.template_filter('short_date')
    def short_date_filter(dt):
        if dt is None:
            return "未知时间"
        try:
            return dt.strftime('%m-%d %H:%M')
        except Exception:
            return "时间错误"

    # 创建数据库表
    with app.app_context():
        db.create_all()
        # 创建默认学习库（如果不存在）
        if not Deck.query.first():
            default_deck = Deck(name="默认学习库", description="系统默认学习库")
            db.session.add(default_deck)
            db.session.commit()
        # 创建默认用户（如果不存在）
        if not User.query.first():
            user = User(username='admin')
            user.set_password('password')  # 默认密码
            db.session.add(user)
            db.session.commit()

    return app


app = create_app()


# 登录装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# ========== 登录路由 ==========

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='用户名或密码错误')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))


# ========== 页面路由 ==========


@app.route('/')
@login_required
def index():
    """首页"""
    decks = Deck.query.filter_by(is_active=True).all()
    total_content = Content.query.count()

    # 获取最近的学习会话
    recent_sessions = StudySession.query.order_by(StudySession.created_at.desc()).limit(5).all()

    # 计算每个学习集的学习统计
    for deck in decks:
        # 已学习内容数（有学习状态记录的内容）
        learned_count = ContentStatus.query.join(Content).filter(
            Content.deck_id == deck.id
        ).count()
        setattr(deck, 'learned_count', learned_count)
    # 今日学习记录数
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())

    today_records = StudyRecord.query.filter(
        StudyRecord.studied_at >= today_start
    ).count()

    # 今日正确回答数
    today_correct = StudyRecord.query.filter(
        StudyRecord.studied_at >= today_start,
        StudyRecord.is_correct == 1
    ).count()

    # 计算正确率
    accuracy_rate = 0
    if today_records > 0:
        accuracy_rate = round((today_correct / today_records) * 100, 1)

    return render_template('index.html',
                           decks=decks,
                           total_content=total_content,
                           recent_sessions=recent_sessions,
                           today_study_count=today_records,
                           accuracy_rate=accuracy_rate)


@app.route('/decks')
@login_required
def decks():
    """学习库管理页面"""
    decks = Deck.query.filter_by(is_active=True).all()
    return render_template('decks.html', decks=decks)


@app.route('/study/setup/<int:deck_id>')
@login_required
def study_setup(deck_id):
    """学习设置页面"""
    deck = Deck.query.get_or_404(deck_id)

    # 统计学习库内容
    total_content = Content.query.filter_by(deck_id=deck_id).count()

    # 统计已学习内容
    learned_content = ContentStatus.query.join(Content).filter(
        Content.deck_id == deck_id
    ).count()

    # 统计待复习内容
    due_review = ContentStatus.query.join(Content).filter(
        Content.deck_id == deck_id,
        ContentStatus.next_review <= datetime.now(),
        ContentStatus.status != 'too_easy'
    ).count()

    # 统计已掌握内容
    mastered_content = ContentStatus.query.join(Content).filter(
        Content.deck_id == deck_id,
        ContentStatus.status == 'mastered'
    ).count()

    return render_template('study_setup.html',
                           deck=deck,
                           total_content=total_content,
                           learned_content=learned_content,
                           due_review=due_review,
                           mastered_content=mastered_content)


@app.route('/study/session/<int:session_id>')
@login_required
def study_session(session_id):
    """学习会话页面"""
    session = StudySession.query.get_or_404(session_id)
    return render_template('study_session.html', session=session)


@app.route('/study/stats/<int:session_id>')
@login_required
def study_stats(session_id):
    """学习统计页面"""
    session = StudySession.query.get_or_404(session_id)
    return render_template('study_stats.html', session=session)


# ========== API路由 ==========

# 学习库管理API
@app.route('/api/decks', methods=['GET'])
@login_required
def get_decks():
    """获取所有学习库"""
    decks = Deck.query.filter_by(is_active=True).all()
    return jsonify({
        'success': True,
        'data': [{
            'id': deck.id,
            'name': deck.name,
            'description': deck.description,
            'content_count': len(deck.contents)
        } for deck in decks]
    })


@app.route('/api/decks', methods=['POST'])
@login_required
def create_deck():
    """创建学习库"""
    try:
        data = request.get_json()

        if not data.get('name'):
            return jsonify({'success': False, 'message': '学习库名称不能为空'}), 400

        new_deck = Deck(
            name=data['name'],
            description=data.get('description', '')
        )

        db.session.add(new_deck)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '学习库创建成功',
            'data': {'id': new_deck.id, 'name': new_deck.name}
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'}), 500


# 内容管理API
@app.route('/api/content/<int:deck_id>', methods=['GET'])
@login_required
def get_content(deck_id):
    """获取学习库内容"""
    contents = Content.query.filter_by(deck_id=deck_id).all()
    return jsonify({
        'success': True,
        'data': [content.to_dict() for content in contents]
    })


@app.route('/api/content/<int:deck_id>', methods=['POST'])
@login_required
def add_content(deck_id):
    """添加内容到学习库"""
    try:
        data = request.get_json()

        required_fields = ['type', 'front', 'back']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'缺少必要字段: {field}'}), 400

        new_content = Content(
            deck_id=deck_id,
            type=data['type'],
            front=data['front'],
            back=data['back'],
            example=data.get('example', ''),
            unit=data.get('unit', ''),          # 新增字段
            page=data.get('page', ''),          # 新增字段
            order=data.get('order', 0)          # 新增字段
        )

        db.session.add(new_content)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '内容添加成功',
            'data': new_content.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'}), 500


@app.route('/api/content/<int:content_id>', methods=['DELETE'])
@login_required
def delete_content(content_id):
    """删除内容"""
    try:
        content = Content.query.get_or_404(content_id)

        # 先删除关联的ContentStatus记录
        if content.status:
            db.session.delete(content.status)

        # 再删除内容本身
        db.session.delete(content)
        db.session.commit()

        return jsonify({'success': True, 'message': '内容删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500

# 在 app.py 中添加统一学习页面路由
@app.route('/study/unified/<int:deck_id>')
@login_required
def unified_study(deck_id):
    """统一学习页面"""
    deck = Deck.query.get_or_404(deck_id)
    return render_template('unified_study.html', deck=deck)

# 在 app.py 的 start_unified_study 函数中修改
@app.route('/api/study/unified/start', methods=['POST'])
@login_required
def start_unified_study():
    """开始统一学习"""
    try:
        data = request.get_json()
        deck_id = data['deck_id']
        # 从学习配置中获取每日目标，如果没有配置则使用默认值20
        study_config = StudyConfig.query.filter_by(deck_id=deck_id).first()
        daily_goal = study_config.daily_goal if study_config else data.get('daily_goal', 20)

        # 检查是否有未完成的学习批次
        existing_batch = StudyBatch.query.filter_by(
            user_id=session['user_id'],
            deck_id=deck_id,
            is_completed=False
        ).first()

        if existing_batch:
            # 继续之前的学习批次
            batch = existing_batch
            # 检查剩余内容是否足够
            remaining_content = select_study_content_with_progress(
                deck_id,
                daily_goal,
                batch.current_index
            )
            # 如果剩余内容不足目标数量，创建新的批次来补充
            if len(remaining_content) < daily_goal:
                # 创建新批次来补充学习内容
                new_batch = StudyBatch(
                    user_id=session['user_id'],
                    deck_id=deck_id,
                    started_at=datetime.utcnow(),
                    current_index=0
                )
                db.session.add(new_batch)
                db.session.flush()

                # 合并剩余内容和新内容
                additional_content = select_study_content_with_progress(
                    deck_id,
                    daily_goal - len(remaining_content),
                    0
                )
                study_content = remaining_content + additional_content

                # 更新批次信息
                batch = new_batch
            else:
                study_content = remaining_content
        else:
            # 创建新的学习批次
            batch = StudyBatch(
                user_id=session['user_id'],
                deck_id=deck_id,
                started_at=datetime.utcnow(),
                current_index=0
            )
            db.session.add(batch)
            db.session.flush()
            # 选择学习内容（考虑当前位置）
            study_content = select_study_content_with_progress(
                deck_id,
                daily_goal,
                batch.current_index
            )

        if not study_content:
            return jsonify({'success': False, 'message': '没有可学习的内容'}), 400

        # 获取学习库配置
        config = StudyConfig.query.filter_by(deck_id=deck_id).first()
        study_order = config.study_order if config else 'zh_first'

        content_list = []
        for content_type, content in study_content:
            if study_order == 'zh_first':
                display_text = content.back
                answer = content.front
                input_placeholder = "请输入英文..."
            else:
                display_text = content.front
                answer = content.back
                input_placeholder = "请输入中文翻译..."

            content_list.append({
                'id': content.id,
                'type': content_type,
                'display_text': display_text,
                'answer': answer,
                'example': content.example,
                'input_placeholder': input_placeholder
            })

        db.session.commit()

        return jsonify({
            'success': True,
            'batch_id': batch.id,
            'content': content_list,
            'current_index': batch.current_index,
            'total_items': len(content_list),
            'daily_goal': daily_goal  # 返回每日目标给前端
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'开始学习失败: {str(e)}'}), 500

@app.route('/api/study/unified/record', methods=['POST'])
@login_required
def record_unified_study():
    """记录统一学习进度 - 使用艾宾浩斯记忆曲线"""
    try:
        from utils import update_content_status_based_on_ebbinghaus

        data = request.get_json()
        batch_id = data['batch_id']
        content_id = data['content_id']
        deck_id = data['deck_id']
        feedback_type = data['feedback_type']
        user_input = data.get('user_input', '')
        response_time = data.get('response_time', 0)
        is_correct = data.get('is_correct', False)

        # 获取或创建学习批次
        batch = StudyBatch.query.get(batch_id)
        if not batch:
            batch = StudyBatch(
                id=batch_id,
                user_id=session['user_id'],
                deck_id=deck_id,
                started_at=datetime.now(),
                is_completed=False
            )
            db.session.add(batch)
            db.session.flush()

        # 创建学习记录
        record = StudyRecord(
            batch_id=batch_id,
            content_id=content_id,
            user_input=user_input,
            response_time=response_time,
            feedback_type=feedback_type,
            is_correct=is_correct
        )
        db.session.add(record)

        # 更新批次位置
        batch.current_index += 1

        # 更新内容状态（使用艾宾浩斯算法）
        status = ContentStatus.query.filter_by(content_id=content_id).first()
        if not status:
            status = create_content_status(content_id)
            db.session.add(status)

        # 根据反馈类型映射到艾宾浩斯质量评分
        quality_mapping = {
            'too_easy': 5,      # 完全掌握
            'remembered': 4,    # 正确回答
            'forgotten': 2      # 错误回答
        }
        quality = quality_mapping.get(feedback_type, 3)

        # 应用艾宾浩斯记忆曲线更新
        update_content_status_based_on_ebbinghaus(status, quality, response_time)

        status.last_reviewed = datetime.now()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '学习记录已保存'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'记录失败: {str(e)}'}), 500

# 学习会话API
@app.route('/api/study/start', methods=['POST'])
@login_required
def start_study_session():
    """开始学习会话"""
    try:
        data = request.get_json()
        deck_id = data['deck_id']
        daily_goal = data.get('daily_goal', 20)

        # 选择学习内容
        study_content = select_study_content(deck_id, daily_goal)

        if not study_content:
            return jsonify({'success': False, 'message': '没有可学习的内容'}), 400

        # 创建学习会话
        session = StudySession(
            deck_id=deck_id,
            duration=0,
            total_items=len(study_content),
            daily_goal=daily_goal
        )
        db.session.add(session)
        db.session.flush()  # 获取session.id但不提交

        # 为新内容创建学习状态记录
        for content_type, content in study_content:
            if content_type == 'new':
                existing_status = ContentStatus.query.filter_by(content_id=content.id).first()
                if not existing_status:
                    status = create_content_status(content.id)
                    db.session.add(status)

        db.session.commit()

        return jsonify({
            'success': True,
            'session_id': session.id,
            'content': [{
                'id': content.id,
                'type': content_type,
                'front': content.front,
                'back': content.back,
                'example': content.example
            } for content_type, content in study_content]
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'开始学习失败: {str(e)}'}), 500


# 在 app.py 中添加获取学习会话详情的API
@app.route('/api/study/session/<int:session_id>')
def get_study_session_details(session_id):
    """获取学习会话详细信息"""
    session = StudySession.query.get_or_404(session_id)

    # 如果学习已完成，返回完成状态
    if session.completed:
        return jsonify({
            'success': True,
            'completed': True,
            'message': '学习已完成'
        })

    # 获取学习库配置
    config = StudyConfig.query.filter_by(deck_id=session.deck_id).first()
    daily_goal = config.daily_goal if config else 20

    # 选择学习内容（考虑当前进度）
    study_content = select_study_content_with_progress(session.deck_id, daily_goal, session.current_index)

    content_list = []
    for content_type, content in study_content:
        # 根据配置决定显示方式
        study_order = config.study_order if config else 'zh_first'
        if study_order == 'zh_first':
            display_text = content.back
            answer = content.front
            input_placeholder = "请输入英文..."
        else:
            display_text = content.front
            answer = content.back
            input_placeholder = "请输入中文翻译..."

        content_list.append({
            'id': content.id,
            'type': content_type,
            'display_text': display_text,
            'answer': answer,
            'example': content.example,
            'input_placeholder': input_placeholder
        })

    return jsonify({
        'success': True,
        'completed': False,
        'content': content_list,
        'current_index': session.current_index,
        'total_items': session.total_items
    })


# 在 app.py 中添加新路由
@app.route('/api/study/mark_too_easy', methods=['POST'])
@login_required
def mark_content_too_easy():
    """标记内容为太简单"""
    try:
        data = request.get_json()
        content_id = data['content_id']
        session_id = data['session_id']

        # 获取或创建内容状态
        status = ContentStatus.query.filter_by(content_id=content_id).first()
        if not status:
            status = create_content_status(content_id)
            db.session.add(status)

        # 标记为太简单
        status.status = 'too_easy'
        status.memory_strength = 1.0
        status.next_review = datetime.now() + timedelta(days=365)  # 一年后才出现

        # 更新学习会话统计
        session = StudySession.query.get(session_id)
        if session:
            session.easy_items += 1

        db.session.commit()

        return jsonify({'success': True, 'message': '已标记为太简单'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'标记失败: {str(e)}'}), 500


@app.route('/api/study/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """提交学习反馈"""
    try:
        data = request.get_json()
        content_id = data['content_id']
        feedback_type = data['feedback_type']
        response_time = data.get('response_time', 0)
        session_id = data['session_id']

        # 获取或创建内容状态
        status = ContentStatus.query.filter_by(content_id=content_id).first()
        if not status:
            status = create_content_status(content_id)
            db.session.add(status)

        # 更新内容状态
        if feedback_type == 'too_easy':
            status.status = 'too_easy'
            status.memory_strength = 1.0
            status.next_review = datetime.now() + timedelta(days=365)
        elif feedback_type == 'remembered':
            status.review_count += 1
            status.correct_count += 1
            status.memory_strength = min(1.0, status.memory_strength + 0.2)

            if status.interval == 0:
                status.interval = 1
            else:
                status.interval = status.interval * 2

            status.next_review = datetime.now() + timedelta(days=status.interval)
        elif feedback_type == 'forgotten':
            status.review_count += 1
            status.correct_count = 0
            status.memory_strength = max(0.0, status.memory_strength - 0.3)
            status.interval = max(1, status.interval // 2)
            status.next_review = datetime.now() + timedelta(days=status.interval)

        status.last_reviewed = datetime.now()
        status.total_time += response_time

        # 更新学习会话进度
        session = StudySession.query.get(session_id)
        if session:
            session.current_index += 1  # 移动到下一个内容

            # 检查是否已完成
            if session.current_index >= session.total_items:
                session.completed = True
                session.ended_at = datetime.now()

            # 更新统计
            if status.review_count == 1:
                session.new_items += 1
            else:
                session.reviewed_items += 1

            if feedback_type == 'remembered':
                session.correct_answers += 1

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '反馈提交成功',
            'completed': session.completed if session else False
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'反馈提交失败: {str(e)}'}), 500


@app.route('/api/study/end', methods=['POST'])
@login_required
def end_study_session():
    """结束学习会话"""
    try:
        data = request.get_json()
        session_id = data['session_id']

        session = StudySession.query.get(session_id)
        if session:
            session.ended_at = datetime.now()
            db.session.commit()

        return jsonify({'success': True, 'message': '学习会话结束'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'结束会话失败: {str(e)}'}), 500


# 系统状态检查
@app.route('/health')
@login_required
def health_check():
    """健康检查"""
    try:
        # 测试数据库连接
        db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500


# 在 app.py 的 API 路由部分添加以下代码

@app.route('/api/content/batch_import/<int:deck_id>', methods=['POST'])
@login_required
def batch_import_content(deck_id):
    """批量导入内容"""
    try:
        data = request.get_json()

        if not isinstance(data, list):
            return jsonify({'success': False, 'message': '数据格式错误，必须是数组'}), 400

        results = {
            'total': len(data),
            'success': 0,
            'error': 0,
            'errors': []
        }

        for index, item in enumerate(data):
            try:
                # 验证必要字段
                required_fields = ['type', 'front', 'back']
                for field in required_fields:
                    if not item.get(field):
                        raise ValueError(f'缺少必要字段: {field}')

                # 创建内容
                new_content = Content(
                    deck_id=deck_id,
                    type=item['type'],
                    front=item['front'],
                    back=item['back'],
                    example=item.get('example', '')
                )

                db.session.add(new_content)
                db.session.flush()  # 获取ID但不提交事务

                results['success'] += 1

            except Exception as e:
                results['error'] += 1
                results['errors'].append(f'第 {index + 1} 条: {str(e)}')

        # 提交所有成功的内容
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'批量导入完成，成功 {results["success"]} 条，失败 {results["error"]} 条',
            'data': results
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'批量导入失败: {str(e)}'}), 500


@app.route('/content/<int:deck_id>')
@login_required
def content_management(deck_id):
    """内容管理页面"""
    deck = Deck.query.get_or_404(deck_id)
    # 获取页码参数，默认第1页
    page = request.args.get('page', 1, type=int)
    per_page = 10  # 每页显示10条内容

    # 获取内容及其学习状态，支持分页
    contents_query = Content.query.filter_by(deck_id=deck_id) \
        .outerjoin(ContentStatus) \
        .order_by(Content.id)
    # 分页查询
    contents_paginated = contents_query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    return render_template('content.html',
                         deck=deck,
                         contents=contents_paginated.items,
                         pagination=contents_paginated)


# 在 app.py 中添加以下路由
# 在 app.py 中修改 practice 路由
@app.route('/practice/<int:deck_id>')
@login_required
def practice(deck_id):
    """背诵练习页面 - 重定向到统一学习页面"""
    return redirect(url_for('unified_study', deck_id=deck_id))


@app.route('/api/practice/next_content/<int:deck_id>')
@login_required
def get_next_content(deck_id):
    """获取下一个学习内容（简单顺序读取）"""
    # 获取请求参数
    current_content_id = request.args.get('current_content_id', type=int)
    mode = request.args.get('mode', 'en_to_zh')  # en_to_zh: 英文->中文, zh_to_en: 中文->英文

    # 查询学习库中的所有内容
    all_contents = Content.query.filter_by(deck_id=deck_id).order_by(Content.id).all()

    if not all_contents:
        return jsonify({
            'success': False,
            'message': '学习库中没有内容'
        })

    # 确定下一个内容的索引
    if current_content_id:
        # 查找当前内容在列表中的位置
        current_index = next((i for i, c in enumerate(all_contents) if c.id == current_content_id), -1)
        next_index = (current_index + 1) % len(all_contents)
    else:
        # 如果没有当前内容，从第一个开始
        next_index = 0

    next_content = all_contents[next_index]

    # 根据模式准备数据
    if mode == 'en_to_zh':
        # 英文->中文：显示英文，默写中文
        display_text = next_content.front
        answer = next_content.back
        input_placeholder = "请输入中文翻译..."
    else:
        # 中文->英文：显示中文，默写英文
        display_text = next_content.back
        answer = next_content.front
        input_placeholder = "请输入英文..."

    return jsonify({
        'success': True,
        'content': {
            'id': next_content.id,
            'display_text': display_text,
            'answer': answer,
            'example': next_content.example,
            'type': next_content.type,
            'input_placeholder': input_placeholder
        },
        'progress': {
            'current': next_index + 1,
            'total': len(all_contents)
        }
    })


@app.route('/api/practice/feedback', methods=['POST'])
@login_required
def practice_feedback():
    """处理学习反馈"""
    try:
        data = request.get_json()
        content_id = data['content_id']
        feedback_type = data['feedback_type']  # 'too_easy', 'correct', 'incorrect'
        user_answer = data.get('user_answer', '')

        # 获取或创建内容状态
        status = ContentStatus.query.filter_by(content_id=content_id).first()
        if not status:
            status = ContentStatus(content_id=content_id)
            db.session.add(status)

        # 处理反馈
        if feedback_type == 'too_easy':
            status.status = 'too_easy'
            status.memory_strength = 1.0
        elif feedback_type == 'correct':
            status.review_count += 1
            status.correct_count += 1
            status.memory_strength = min(1.0, status.memory_strength + 0.2)

            # 简单间隔计算
            if status.interval == 0:
                status.interval = 1
            else:
                status.interval = status.interval * 2

            status.next_review = datetime.now() + timedelta(days=status.interval)
        elif feedback_type == 'incorrect':
            status.review_count += 1
            status.correct_count = 0
            status.memory_strength = max(0.0, status.memory_strength - 0.3)
            status.interval = max(1, status.interval // 2)
            status.next_review = datetime.now() + timedelta(days=status.interval)

        status.last_reviewed = datetime.now()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '反馈已记录'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'反馈失败: {str(e)}'
        }), 500


# 在 app.py 中添加学习配置API

@app.route('/api/study/config/<int:deck_id>', methods=['GET'])
@login_required
def get_study_config(deck_id):
    """获取学习配置"""
    config = StudyConfig.query.filter_by(deck_id=deck_id).first()

    if config:
        return jsonify({
            'success': True,
            'data': {
                'mode': config.mode,
                'is_configured': config.is_configured
            }
        })
    else:
        return jsonify({
            'success': True,
            'data': {
                'mode': 'en_to_zh',
                'is_configured': False
            }
        })


@app.route('/api/study/config/<int:deck_id>', methods=['POST'])
@login_required
def save_study_config(deck_id):
    """保存学习配置"""
    try:
        data = request.get_json()
        mode = data.get('mode', 'en_to_zh')
        daily_goal = data.get('daily_goal', 20)
        study_order = data.get('study_order', 'zh_first')
        # 查找或创建配置
        config = StudyConfig.query.filter_by(deck_id=deck_id).first()
        if not config:
            config = StudyConfig(
                deck_id=deck_id,
                daily_goal=daily_goal,
                study_order=study_order,
                is_configured=True
            )
            db.session.add(config)
        else:
            config.daily_goal = daily_goal
            config.study_order = study_order
            config.is_configured = True

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '学习配置已保存'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'保存配置失败: {str(e)}'
        }), 500


# 在 app.py 中添加智能学习入口
@app.route('/learn/<int:deck_id>')
@login_required
def learn(deck_id):
    """智能学习入口 - 直接跳转到统一学习页面"""
    deck = Deck.query.get_or_404(deck_id)
    # 直接跳转到统一学习页面
    return redirect(url_for('unified_study', deck_id=deck_id))


# 添加新的API端点

@app.route('/api/study/batch/start', methods=['POST'])
@login_required
def start_study_batch():
    """开始学习批次"""
    try:
        data = request.get_json()
        deck_id = data['deck_id']
        daily_goal = data.get('daily_goal', 20)
        print("进来了--1--deck_id1：",deck_id)
        # 检查是否有未完成的批次
        existing_batch = StudyBatch.query.filter_by(
            user_id=session['user_id'],
            deck_id=deck_id,
            is_completed=False
        ).first()
        print("进来了--2--existing_batch：", existing_batch)
        if existing_batch:
            # 继续之前的批次
            print("进来了IF--3--existing_batch：", existing_batch)
            batch = existing_batch
        else:
            # 创建新的学习批次
            batch = StudyBatch(
                user_id=session['user_id'],
                deck_id=deck_id,
                started_at=datetime.now(),
                current_index=1
            )
            print("进来了IF--4--existing_batch：", existing_batch)
            db.session.add(batch)
            db.session.flush()
        print("进来了--5--batch.id：", batch.id)
        # 选择学习内容（考虑当前位置）
        study_content = select_study_content_with_progress(
            deck_id,
            daily_goal,
            batch.current_index
        )

        if not study_content:
            return jsonify({'success': False, 'message': '没有可学习的内容'}), 400

        # 获取学习库配置
        config = StudyConfig.query.filter_by(deck_id=deck_id).first()
        study_order = config.study_order if config else 'zh_first'

        content_list = []
        for content_type, content in study_content:
            if study_order == 'zh_first':
                display_text = content.back
                answer = content.front
                input_placeholder = "请输入英文..."
            else:
                display_text = content.front
                answer = content.back
                input_placeholder = "请输入中文翻译..."

            content_list.append({
                'id': content.id,
                'type': content_type,
                'display_text': display_text,
                'answer': answer,
                'example': content.example,
                'input_placeholder': input_placeholder
            })
        # 添加这行来提交事务
        db.session.commit()
        return jsonify({
            'success': True,
            'batch_id': batch.id,
            'content': content_list,
            'current_index': batch.current_index,
            'total_items': len(content_list)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'开始学习失败: {str(e)}'}), 500


@app.route('/api/study/batch/record', methods=['POST'])
def record_study_progress():
    """记录学习进度"""

    print("进来了：")
    try:
        data = request.get_json()
        desk_id=data['desk_id']
        batch_id = data['batch_id']
        content_id = data['content_id']
        feedback_type = data['feedback_type']
        user_input = data.get('user_input', '')
        response_time = data.get('response_time', 0)
        is_correct = data.get('is_correct', False)
        print("进来了batch_id：",batch_id)
        batch = StudyBatch.query.get(batch_id)
        if not batch:
            # 如果批次不存在，创建一个新的
            batch = StudyBatch(
                batch_id=batch_id,
                user_id=session['user_id'],
                deck_id=desk_id,
                started_at=datetime.now(),
                is_completed=False
            )
            db.session.add(batch)
            db.session.flush()

        print("进来了batch：", batch.id)
        # 创建学习记录
        record = StudyRecord(
            batch_id=batch_id,
            content_id=content_id,
            user_input=user_input,
            response_time=response_time,
            feedback_type=feedback_type,
            is_correct=is_correct
        )
        db.session.add(record)
        print("进来了：2")
        # 更新批次位置
        batch.current_index += 1

        # 更新内容状态（复用现有逻辑）
        status = ContentStatus.query.filter_by(content_id=content_id).first()
        if not status:
            status = create_content_status(content_id)
            db.session.add(status)
        print("进来了：3")
        # 应用记忆算法更新
        if feedback_type == 'too_easy':
            status.status = 'too_easy'
            status.memory_strength = 1.0
            status.next_review = datetime.now() + timedelta(days=365)
        elif feedback_type == 'remembered':
            status.review_count += 1
            status.correct_count += 1
            status.memory_strength = min(1.0, status.memory_strength + 0.2)

            if status.interval == 0:
                status.interval = 1
            else:
                status.interval = status.interval * 2

            status.next_review = datetime.now() + timedelta(days=status.interval)
        elif feedback_type == 'forgotten':
            status.review_count += 1
            status.correct_count = 0
            status.memory_strength = max(0.0, status.memory_strength - 0.3)
            status.interval = max(1, status.interval // 2)
            status.next_review = datetime.now() + timedelta(days=status.interval)
        print("进来了：4")
        status.last_reviewed = datetime.now()
        status.total_time += response_time

        db.session.commit()
        print("进来了：5")
        return jsonify({
            'success': True,
            'message': '学习记录已保存'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'记录失败: {str(e)}'}), 500


@app.route('/api/study/batch/complete', methods=['POST'])
@login_required
def complete_study_batch():
    """完成学习批次"""
    try:
        data = request.get_json()
        batch_id = data['batch_id']

        batch = StudyBatch.query.get_or_404(batch_id)
        batch.is_completed = True
        batch.completed_at = datetime.now()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '学习批次已完成'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'完成批次失败: {str(e)}'}), 500


@app.route('/study/batch/<int:deck_id>')
@login_required
def batch_study(deck_id):
    """批次学习页面"""
    print("deck_id:", deck_id)
    deck = Deck.query.get_or_404(deck_id)
    print("deck:", deck.id)
    return render_template('batch_study.html', deck=deck)


@app.route('/api/study/unified/update_duration', methods=['POST'])
@login_required
def update_study_duration():
    """更新学习批次时长"""
    try:
        data = request.get_json()
        batch_id = data['batch_id']
        duration = data['duration']

        batch = StudyBatch.query.get_or_404(batch_id)
        if batch:
            batch.total_duration = (batch.total_duration or 0) + duration
            db.session.commit()

        return jsonify({
            'success': True,
            'message': '学习时长已更新'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'}), 500

@app.route('/api/study/unified/complete', methods=['POST'])
@login_required
def complete_unified_study():
    """完成统一学习"""
    try:
        data = request.get_json()
        batch_id = data['batch_id']

        batch = StudyBatch.query.get_or_404(batch_id)
        batch.is_completed = True
        batch.completed_at = datetime.now()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '学习已完成',
            'total_duration': batch.total_duration
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'完成学习失败: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], host='0.0.0.0', port=5000)
