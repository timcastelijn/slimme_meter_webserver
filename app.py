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

# function to return the number using regex
def getValue(line):
    try:
        value = re.search("\(([0-9.]+)\*", line).group(1)
        return value
    except:
        return None

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
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
db = None

codes = [
    {'code':'1-0:1.8.1',    'name':'afname totaal dal',   'id':'usage_total_low',     'unit': 'kWh'},
    {'code':'1-0:1.8.2',    'name': 'afname totaal piek',  'id':'usage_total_high',    'unit': 'kWh'},
    {'code':'1-0:2.8.1',    'name': 'teruggeleverd dal',   'id':'returned_total_high', 'unit': 'kWh'},
    {'code':'1-0:2.8.2',    'name': 'teruggeleverd piek',  'id':'returned_total_low',  'unit': 'kWh'},
    {'code':'1-0:1.7.0',    'name': 'verbruik huidig',     'id':'usage_current',       'unit': 'kW'},
    {'code':'1-0:2.7.0',    'name': 'teruggeleverd huidig','id':'returned_current',    'unit': 'kW'},
    {'code':'0-1:24.2.1',   'name': 'verbruik totaal Gas', 'id':'usage_total_gas',     'unit': 'm3'},
]

def background_thread():
    """Example of how to send server generated events to clients."""
    # ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=5)
    ser = serial.Serial("/dev/tty.usbserial-A1014RK3", 115200, timeout=5)

    # create database
    global db
    db = leveldb.LevelDB('./db')

    # wiat a bit
    time.sleep(4)

    p1_raw = "/n"
    last_save = 0
    while True:

        line = ser.readline()
        store_values = False
        localtime = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())

        if line:


            if (time.time() > last_save + 30):
                store_values = True
                last_save = time.time()
                print "save"

            for table in codes:
                if table['code'] in line:
                    value = getValue(line)
                    print value
                    if value:
                        db.Put('last/%s'%table['id'], value)
                        if store_values:
                            db.Put('data/%s/%s'%(table['id'], localtime),value)
                else:
                    pass

        else:

            print 'print values from db %s'%localtime
            response = {}
    	    for item in db.RangeIter(key_from = 'last', key_to = 'last~'):
                print item
                key = item[0].split('/')[-1]
                response[key] = item[1]

            socketio.emit('my response',
                {'data': response, 'count': item[0]},
                namespace='/test')


@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('my event', namespace='/test')
def test_message(message):
    print 'my event'

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

    response = {}
    for item in db.RangeIter(key_from = 'last', key_to = 'last~'):
        print item
        response[item[0]] = item[1]

    emit('my response',
            {'data': response, 'count': item[0]})


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
