from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MySQL 연결 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/testdb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 모델 정의
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    flag = db.Column(db.Integer, default=0)
    
class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    vote_value = db.Column(db.String(10))  # 예: 'up', 'down'

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    menu = db.Column(db.String(50), unique=True, nullable=False)
    count = db.Column(db.Integer, default=0)

# vote 테이블 초기화 함수
def initialize_vote_table():
    with app.app_context():
        if not db.session.query(Vote).first():
            db.session.add_all([
                Vote(menu='chicken', count=0),
                Vote(menu='tteok', count=0)
            ])
            db.session.commit()

# 테이블 생성 및 초기화
with app.app_context():
    db.create_all()
    initialize_vote_table()

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']

        if User.query.filter_by(email=email).first():
            return '이미 존재하는 이메일입니다.'

        new_user = User(email=email)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if user:
            session['user_id'] = user.id
            return redirect(url_for('vote'))
        return '존재하지 않는 이메일입니다.'

    return render_template('login.html')


@app.route('/vote', methods=['GET', 'POST'])
def vote():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    if user.flag == 1:
        return '이미 투표하셨습니다.'

    if request.method == 'POST':
        selected = request.form.get('menu')
        vote_entry = Vote.query.filter_by(menu=selected).first()
        if vote_entry:
            vote_entry.count += 1
            user.flag = 1
            db.session.commit()
            return redirect(url_for('result'))
        else:
            return '잘못된 투표입니다.'

    return render_template('vote.html')

@app.route('/result')
def result():
    votes = Vote.query.all()
    return render_template('result.html', votes=votes)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
