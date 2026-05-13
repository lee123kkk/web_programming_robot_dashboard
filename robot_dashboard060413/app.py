from flask import Flask, jsonify, request, render_template, Response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
import os
import cv2        # [추가] 가상 카메라용
import numpy as np # [추가] 가상 카메라용
import time       # [추가] 가상 카메라용


# 1. 모델 임포트
try:
    from models.robot_state import robot_manager
except ImportError:
    print("Error: models/robot_state.py 파일을 찾을 수 없습니다.")

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

# [수정] MariaDB 대신 WSL에서 즉시 실행 가능한 SQLite로 변경
# 기존 코드: app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://robot_user:0405@localhost/robot_db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///robot_db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 데이터베이스 로그 테이블 모델 정의
class RobotLog(db.Model):
    __tablename__ = 'robot_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=func.now())
    level = db.Column(db.String(20)) # '정상', '주의', '에러'
    message = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "time": self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            "level": self.level,
            "message": self.message
        }

# 테이블이 없으면 자동으로 생성하는 로직
with app.app_context():
    db.create_all()

CORS(app)

# 2. 메인 페이지
@app.route('/')
def index():
    return render_template('index.html')

# 3. 로봇 상태 조회 API
@app.route('/api/robot/status', methods=['GET'])
def get_robot_status():
    return jsonify(robot_manager.get_current_state())

# 로그 저장용 API
@app.route('/api/logs', methods=['POST'])
def save_log():
    data = request.json
    try:
        new_log = RobotLog(
            level=data.get('level', '정상'),
            message=data.get('message', '')
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({"result": "success"})
    except Exception as e:
        print(f"\n[DB ERROR] 로그 저장 중 에러 발생: {e}\n")
        db.session.rollback()
        return jsonify({"result": "error", "message": str(e)}), 500

# 4. 로봇 제어 API
@app.route('/api/robot/control', methods=['POST'])
def control_robot():
    data = request.json
    action = data.get('action')
    direction = data.get('direction')

    if action == 'move':
        robot_manager.state["status"] = "moving"
        robot_manager.state["direction"] = direction
        return jsonify({"result": "success", "status": "moving", "direction": direction})

    elif action == 'stop':
        robot_manager.state["status"] = "idle"
        robot_manager.state["direction"] = None
        return jsonify({"result": "success", "status": "idle"})

    if hasattr(robot_manager, 'update_command'):
        result = robot_manager.update_command(data)
        return jsonify(result)

    return jsonify({"result": "success", "action": action})

@app.route('/api/robot/floor', methods=['POST'])
@app.route('/api/control', methods=['POST'])
def update_floor():
    data = request.json
    new_floor = data.get('floor')
    if new_floor:
        robot_manager.state["location"]["floor"] = new_floor
        return jsonify({"result": "success", "floor": new_floor})
    return jsonify({"result": "success", "action": data.get('action')})

# [수정된 가상 카메라 프레임 생성 제너레이터]
def generate_camera_frames():
    """실시간으로 움직이는 가상의 카메라 영상을 생성하며, 의도적으로 CPU 부하를 크게 발생시킵니다."""
    # 1. 해상도를 대폭 상향 (연산량 증가)
    width, height = 1280, 720 
    box_x, box_y = 640, 360
    dx, dy = 15, 15

    while True:
        # 2. 어두운 배경 생성
        frame = np.ones((height, width, 3), dtype=np.uint8) * 40
        
        # 3. 움직이는 상자 그리기
        box_x += dx
        box_y += dy
        if box_x <= 50 or box_x >= width - 50: dx = -dx
        if box_y <= 50 or box_y >= height - 50: dy = -dy
        cv2.rectangle(frame, (box_x-50, box_y-50), (box_x+50, box_y+50), (0, 255, 0), -1)
        
        # 4. [핵심 부하 생성] 매 프레임마다 무거운 이미지 필터링 반복 연산 (의도적 CPU 낭비)
        for _ in range(3): 
            frame = cv2.GaussianBlur(frame, (31, 31), 0)
        
        # 5. 텍스트 입히기
        current_time = time.strftime("%H:%M:%S")
        status = robot_manager.state.get("status", "UNKNOWN").upper()
        
        cv2.putText(frame, "HEAVY NARCHON V-CAM", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        cv2.putText(frame, f"TIME: {current_time}", (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 2)
        cv2.putText(frame, f"STATUS: {status}", (30, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 2)

        # 6. 이미지 인코딩
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        frame_bytes = buffer.tobytes()

        # 7. 스트리밍 반환
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # 대기 시간 최소화 (더 많은 연산 유도)
        time.sleep(0.01)

# [추가] 웹에서 영상 스트림을 받아가는 엔드포인트
@app.route('/api/camera/stream')
def camera_stream():
    """MJPEG(Multipart/x-mixed-replace) 방식으로 영상을 스트리밍합니다."""
    return Response(generate_camera_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
