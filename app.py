#!/usr/bin/env python

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on available packages.
async_mode = None

if async_mode is None:
    try:
        import eventlet
        async_mode = 'eventlet'
    except ImportError:
        pass

    if async_mode is None:
        try:
            from gevent import monkey
            async_mode = 'gevent'
        except ImportError:
            pass

    if async_mode is None:
        async_mode = 'threading'

    print('async_mode is ' + async_mode)

# monkey patching is necessary because this application uses a background
# thread
if async_mode == 'eventlet':
    import eventlet
    eventlet.monkey_patch()
elif async_mode == 'gevent':
    from gevent import monkey
    monkey.patch_all()

import time
from threading import Thread
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect

import serial
import leveldb

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
db = None

def background_thread():
    """Example of how to send server generated events to clients."""
    ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=5)
    #ser = serial.Serial("/dev/tty.usbserial-A932INF", 115200)

    # create database
    global db
    db = leveldb.LevelDB('./db')

    # wiat a bit
    time.sleep(4)

    p1_raw = "/n"

    count = 0
    while True:

        line = ser.readline()

        count = count + 1
        if line:

            parsed_line = None
            localtime = time.strftime("%Y%m%d_%H%M%S", time.localtime())

            line = line.strip()
            prefix = 'last'


            if "1-0:1.8.1" in line:
                parsed_line = "verbuik totaal dal: %s"% float(line[10:20])
                db.Put('%s/usage_total_low'%prefix,(line[10:20]))
            elif "1-0:1.8.2" in line:
                parsed_line = "verbruik totaal piek: %s"% float(line[10:20])
                db.Put('%s/usage_total_high'%prefix,(line[10:20]))
            elif "1-0:2.8.1" in line:
                parsed_line = "teruggeleverd dal: %s"% float(line[10:20])
                db.Put('%s/returned_total_low'%prefix,(line[10:20]))
            elif "1-0:2.8.2" in line:
                parsed_line = "teruggeleverd piek: %s"% float(line[10:20])
                db.Put('%s/returned_total_high'%prefix,(line[10:20]))
            elif "1-0:1.7.0" in line:
                parsed_line = "verbruik huidig: %s"% float(line[10:16])
                db.Put('%s/usage_current'%prefix,(line[10:16]))
            elif "1-0:2.7.0" in line:
                parsed_line = "teruggeleverd huidig: %s"% float(line[10:16])
                db.Put('%s/returned_current'%prefix,(line[10:16]))
            elif  "0-1:24.2.1" in line:
                parsed_line = "verbruik totaal Gas: %s"% float(line[26:35])
                db.Put('%s/gas_usage_total'%prefix, (line[26:35]))
            else:
                pass

            if parsed_line:
                print parsed_line
                # socketio.emit('my response',
                #         {'data': parsed_line, 'count': "key %s" % localtime},
                #         namespace='/test')
        else:
    	    for item in db.RangeIter(key_from = 'last', key_to = 'last//'):
                emit('my response',
                    {'data': item[1], 'count': item[0]})


@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('my event', namespace='/test')
def test_message(message):
    global db
    for item in db.RangeIter():
        emit('my response',
                {'data': item[1], 'count': item[0]})


@socketio.on('my broadcast event', namespace='/test')
def test_broadcast_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': message['data'], 'count': session['receive_count']},
         broadcast=True)


@socketio.on('join', namespace='/test')
def join(message):
    join_room(message['room'])
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': 'In rooms: ' + ', '.join(rooms()),
          'count': session['receive_count']})

@socketio.on('leave', namespace='/test')
def leave(message):
    leave_room(message['room'])
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': 'In rooms: ' + ', '.join(rooms()),
          'count': session['receive_count']})


@socketio.on('close room', namespace='/test')
def close(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response', {'data': 'Room ' + message['room'] + ' is closing.',
                         'count': session['receive_count']},
         room=message['room'])
    close_room(message['room'])


@socketio.on('my room event', namespace='/test')
def send_room_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': message['data'], 'count': session['receive_count']},
         room=message['room'])

@socketio.on('disconnect request', namespace='/test')
def disconnect_request():
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': 'Disconnected!', 'count': session['receive_count']})
    disconnect()


@socketio.on('connect', namespace='/test')
def test_connect():
    global db
    for item in db.RangeIter(key_from = 'last', key_to = 'last//'):
        emit('my response',
                {'data': item[1], 'count': item[0]})


@socketio.on('disconnect', namespace='/test')
def test_disconnect():
    print('Client disconnected', request.sid)


if __name__ == '__main__':
    global thread
    if thread is None:
        thread = Thread(target=background_thread)
        thread.daemon = True
        thread.start()

    socketio.run(app, host='0.0.0.0', debug=True)
