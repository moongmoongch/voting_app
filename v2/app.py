from flask import Flask, render_template, request, jsonify, make_response, redirect, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from datetime import datetime
import redis
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule
import time
import threading
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# 기본 DB: users.db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

# 추가 DB: vote.db
app.config['SQLALCHEMY_BINDS'] = {
    'vote': 'sqlite:///vote.db'
}

db = SQLAlchemy(app)

# -------------------------------
# ✅ User 모델 (기본 DB에 저장됨)
# -------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    vote_value = db.Column(db.String(10))  

    def __repr__(self):
        return f"User('{self.email}')"

# -------------------------------
# ✅ Vote 모델 (vote.db에 저장됨)
# -------------------------------
class Vote(db.Model):
    __bind_key__ = 'vote'
    id = db.Column(db.Integer, primary_key=True)
    menu = db.Column(db.String(50), unique=True, nullable=False)
    count = db.Column(db.Integer, default=0)

# -------------------------------------
# ✅ Vote 테이블이 없으면 초기화 함수
# -------------------------------------
def initialize_vote_table():
    with app.app_context():
        db.create_all()  # 모든 DB에 대해 테이블 생성
        if not db.session.query(Vote).first():
            db.session.add_all([
                Vote(menu='chicken', count=0),
                Vote(menu='tteokbokki', count=0)
            ])
            db.session.commit()


# 마감 시간 설정
DEADLINE = datetime(2025, 5, 9, 0, 0, 0)

# Redis 연결 설정
redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

# 투표 결과 저장
votes = {"떡볶이": 0, "치킨": 0}

from flask import render_template, request
from datetime import datetime

@app.route('/')
def index():
    user_vote = request.cookies.get('vote')  # 사용자 쿠키에서 투표한 값 가져오기

    # DB에서 투표 결과 가져오기
    vote_data = Vote.query.all()  # Vote는 DB 모델이라 가정

    # 기본값 설정
    tteokbokki_votes = 0
    chicken_votes = 0

    for item in vote_data:
        if item.menu == "tteokbokki":
            tteokbokki_votes = item.count
        elif item.menu == "chicken":
            chicken_votes = item.count

    total_votes = tteokbokki_votes + chicken_votes

    # 퍼센트 계산
    if total_votes == 0:
        tteokbokki_percent = 50
        chicken_percent = 50
    else:
        tteokbokki_percent = round((tteokbokki_votes / total_votes) * 100, 1)
        chicken_percent = round((chicken_votes / total_votes) * 100, 1)

    # 마감 시간 예시 (현재 기준 하루 뒤로 설정)
    deadline = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')

    return render_template(
        'index.html',
        user_vote=user_vote,
        tteokbokki_votes=tteokbokki_votes,
        chicken_votes=chicken_votes,
        tteokbokki=tteokbokki_percent,
        chicken=chicken_percent,
        deadline=deadline
    )


# 딕셔너리 저장
votes = {"tteokbokki": 0, "chicken": 0}


@app.route('/vote', methods=['POST'])
@login_required
def vote():
    user_cookie = request.cookies.get('vote')
    if user_cookie or current_user.vote_value is not None:
        return f"You have already voted. Your choice: {current_user.vote_value or user_cookie}", 400  # 중복 투표 방지

    choice = request.form.get('choice')

    vote_entry = Vote.query.filter_by(menu=choice).first()
    if not vote_entry or choice not in votes:
        return "error: Invalid choice", 400

    try:
        # 투표 수 증가
        votes[choice] += 1
        vote_entry.count += 1

        # 유저 정보 업데이트
        current_user.vote_value = choice

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("DB commit error:", e)
        return "Internal server error", 500

    # 쿠키 설정 및 리다이렉트
    response = make_response(redirect('/results'))
    response.set_cookie('vote', choice, max_age=60*5)  # 5분간 유지
    return response



@app.route('/results', methods=['GET'])
def results():
    vote_data = Vote.query.all()
    total_votes = sum(v.count for v in vote_data)

    if total_votes == 0:
        percentages = {v.menu: 50.0 for v in vote_data}  # 아무도 투표 안 했을 때는 50:50
    else:
        percentages = {
            v.menu: (v.count / total_votes) * 100
            for v in vote_data
        }

    result_json = {}
    for v in vote_data:
        result_json[f"{v.menu}"] = round(percentages[v.menu], 1)
        result_json[f"{v.menu}_votes"] = v.count

    return jsonify(result_json)


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

# Flask-Migrate 초기화
migrate = Migrate(app, db)

# Flask-Login 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"  # 로그인 페이지로 리다이렉트할 URL

   
# 로그인 시 유저 로드 함수
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 로그인 페이지
@app.route("/login_page", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if user:  # 이메일이 데이터베이스에 있으면 로그인 처리
            login_user(user)
            return redirect(url_for('index'))  # 로그인 후 대시보드로 리다이렉트
        else:
            #return "User not found. Please try again."  # 이메일이 없으면 오류 메시지
            error_message="가입된 이메일이 없습니다. 다시 확인해주세요."
            return render_template('login_page.html', error_message=error_message)  # 오류 메시지 전달

    return render_template('login_page.html')  # login.html 렌더링

# 회원가입 페이지
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if user:  # 이메일이 이미 존재하면 오류 메시지 출력
            return render_template('signup.html', message="이메일이 이미 존재합니다. 로그인 페이지로 이동합니다.")
        
        # 새로운 사용자 추가
        new_user = User(email=email)
        db.session.add(new_user)
        db.session.commit()
        return render_template('signup.html', message="회원가입이 완료되었습니다! 로그인 페이지로 이동합니다.")

    return render_template('signup.html')  # signup.html 렌더링

# 로그아웃 처리
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))  # 로그아웃 후 페이지로 리다이렉트

def send_mail_to_voters():
    with app.app_context():
        users = User.query.filter_by(has_voted=True).all()

        # 더 많은 표를 받은 메뉴 계산
        winner = max(votes, key=votes.get)
        vote_count = votes[winner]
        total_votes = sum(votes.values())

        if total_votes == 0:
            result_message = "아직 투표 결과가 없습니다."
        else:
            result_message = f"가장 많은 표를 받은 메뉴는 '{winner}'이며, 총 {vote_count}표를 받았습니다!"

        for user in users:
            from_email = 'sophiang201@gmail.com'
            from_password = 'zrnr kzqk pcei upxc'
            try:
                to_email = user.email
                subject = "투표 결과 안내"
                body = (
                    f"{user.email}님, 안녕하세요!\n\n"
                    f"투표에 참여해주셔서 감사합니다.\n\n"
                    f"{result_message}\n\n"
                    "즐거운 하루 보내세요 :)"
                )

                msg = MIMEMultipart()
                msg['From'] = from_email
                msg['To'] = to_email
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))

                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(from_email, from_password)
                    server.sendmail(from_email, to_email, msg.as_string())
                print(f"메일이 {to_email}로 발송되었습니다.")

            except Exception as e:
                print(f"메일 발송 실패: {e}") 
                

# 특정 시간에 메일 보내기 (쓰레드 사용)
def send_mail_schedule():
    send_time_str = "2025-04-08 21:22:00"  # 메일을 보내고 싶은 시간
    send_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")
    # send_time = datetime.strptime(DEADLINE)  #투표 마감시간에 발송
    current_time = datetime.now()

    # 설정된 시간이 이미 지났다면, 다음 날로 설정
    if send_time < current_time:
        send_time = send_time.replace(day=current_time.day + 1)

    # 이메일 전송 예약 (스케줄러 사용)
    schedule.every().day.at(send_time.strftime("%H:%M")).do(send_mail_to_voters)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()            # 모든 DB(users.db + vote.db) 테이블 생성
        initialize_vote_table()    # vote.db 초기 데이터 넣기
    threading.Thread(target=send_mail_schedule, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
