import json
import os
from os.path import join as _join
from os.path import exists as _exists
from datetime import datetime

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

_this_dir = os.path.dirname(os.path.abspath(__file__))

with open(_join(_this_dir, 'tlx_sart_hybrid.txt')) as fp:
    nasa_tlx_dimensions = [line.strip().split('|') for line in fp]

participants = [f'Participant{i}' for i in range(1, 10)]

scenarios = [f'Scenario{i}' for i in range(1, 10)]

# Assume a global variable to keep track of the survey status
survey_status = 'closed'
survey_name = ''

# Global dictionary to track survey status by participant ID
session_statuses = {}
session_participants = {}
session_lastsave = {}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)


@app.route('/admin')
def admin():
    global scenarios
    return render_template('admin.html',
                           scenarios=scenarios)


@app.route('/')
@app.route('/survey')
def survey():
    global participants, survey_status, survey_name, nasa_tlx_dimensions
    # Pass the dimensions list to the template
    return render_template('survey.html',
                           participants=participants,
                           survey_status=survey_status, 
                           survey_name=survey_name, 
                           dimensions=nasa_tlx_dimensions)


@socketio.on('submit survey')
def handle_survey_submission(data):
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
def handle_survey_partial_submission(data):
    data['session_id'] = request.sid
    data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data['ip'] = request.remote_addr

    print("Received survey submission via Socket.IO:", data)
    
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


def save_survey_data(data):
    global survey_name
    # Assuming data contains participant ID and survey responses
    participant_id = data.get('participantId')
    
    filename = f"survey_data__{survey_name}__{participant_id}__0.json"
    filepath = _join('survey_submissions', survey_name, filename)
    
    # Make sure the directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    i = 1
    while _exists(filepath):
        filepath = _join('survey_submissions', survey_name, f"survey_data__{survey_name}__{participant_id}__{i}.json")
        i += 1
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Data saved for participant {participant_id}")


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
def confirm_open_survey(data):
    session_id = request.sid
    session_statuses[session_id] = data.get('surveyStatus')
    session_participants[session_id] = data.get('participantId')
    update_admin_view()


@socketio.on('open survey')
def handle_open_survey(data):
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

