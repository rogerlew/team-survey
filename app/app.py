import json
import os
from os.path import join as _join
from os.path import exists as _exists
from datetime import datetime
import yaml

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

_this_dir = os.path.dirname(os.path.abspath(__file__))

# load config from config.yaml
with open(_join(_this_dir, 'config.yaml')) as f:
    config = yaml.safe_load(f)


# global variable to keep track of the survey status
survey_status = 'closed'
survey_name = ''

# dictionaries to track survey status by participant ID
session_statuses = {}
session_participants = {}
session_lastsave = {}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)


@app.route('/')
def index():
    global config
    return render_template('index.html', config=config)


@app.route('/admin')
def admin():
    global config
    return render_template('admin.html',
                           scenarios=config['scenarios'])



@app.route('/survey/<group>')
def survey(group: str):
    global config, survey_status, survey_name

    # Pass the dimensions list to the template
    return render_template('survey.html',
                           group=config['groups'][group],
                           survey_status=survey_status, 
                           survey_name=survey_name)



@socketio.on('submit survey')
def handle_survey_submission(data: dict):
    data['session_id'] = request.sid
    data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data['ip'] = request.remote_addr

    print("Received survey submission via Socket.IO:", data)
    
    # Process and save the data as before
    save_survey_data(data)
    
    # Acknowledge receipt of the survey data
    emit('survey response', {'status': 'received', 'message': 'Thank you for your submission.'})

    session_id = request.sid
    session_statuses[session_id] = 'Submitted'
    session_lastsave[session_id] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    update_admin_view()


@socketio.on('submit partial survey')
def handle_survey_partial_submission(data: dict):
    data['session_id'] = request.sid
    data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data['ip'] = request.remote_addr

    session_id = request.sid
    session_lastsave[session_id] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Process and save the data as before
    save_survey_data(data)
    

def update_admin_view():
    global session_statuses, session_participants

    data = [(session_id, session_participants.get(session_id, '-'), status) 
            for session_id, status in session_statuses.items() if session_id in session_participants]
    
    # only show sessions with Participant IDs
    data = [obj for obj in data if obj[1]]

    # ignore disconnected sessions
    data = [obj for obj in data if obj[2] != 'Disconnected']

    print('updating admin view', data)
    emit('update admin view', data, broadcast=True, include_self=True)


def save_survey_data(data: dict):
    global survey_name
    # Assuming data contains participant ID and survey responses
    participant_id = data.get('participantId')
    
    filename = f"survey_data__{survey_name}__{participant_id}__0.json"
    filepath = _join(_this_dir, 'survey_submissions', survey_name, filename)
    
    # Make sure the directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Data saved for participant {participant_id}")


@app.route('/survey_responses/<survey_name>/<participant_id>')
def get_survey_responses(survey_name: str, participant_id: str):
    
    filename = f"survey_data__{survey_name}__{participant_id}__0.json"
    filepath = _join(_this_dir, 'survey_submissions', survey_name, filename)

    if not _exists(filepath):
        return jsonify({})
    
    with open(filepath) as f:
        data = json.load(f)
    return jsonify( {d['name']: d['value'] for d in data['responses']} )


@socketio.on('connect')
def socket_connect():
    session_id = request.sid
    session_statuses[session_id] = 'Connected'
    print('Client connected')


@socketio.on('disconnect')
def socket_disconnect():
    session_id = request.sid
    session_statuses[session_id] = 'Disconnected'
    print('Client disconnected')
    update_admin_view()


@socketio.on('confirm survey')
def confirm_open_survey(data: dict):
    session_id = request.sid
    session_statuses[session_id] = data.get('surveyStatus')
    session_participants[session_id] = data.get('participantId')
    update_admin_view()


@socketio.on('open survey')
def handle_open_survey(data: dict):
    global survey_status, survey_name
    survey_status = 'open'
    survey_name = data

    print(f"Survey opened: {survey_name}")
    emit('survey status', {'status': survey_status, 'name': survey_name}, broadcast=True)


@socketio.on('close survey')
def handle_close_survey():
    global survey_status, survey_name
    survey_status = 'closed'
    survey_name = ''
    print("Survey closed")
    emit('survey status', {'status': survey_status, 'name': survey_name}, broadcast=True)


if __name__ == '__main__':
    socketio.run(app, debug=True)
