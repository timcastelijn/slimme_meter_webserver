#!/usr/bin/env python

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on available packages.

## copy to pi with
# scp -r ~/Documents/programming/slimme_meter_webserver pi@raspberrypi.local:~/slimme_meter
## add to scheduled tasks with
# sudo crontab -e

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

previous={
    'usage_total_low':{},
    'usage_total_high':{},
}

def storeValues(values):

    global db

    localtime = time.strftime("%Y/%m/%d/%H/%M", time.localtime())

    timeset = [
        # {'subunit':5, 'id':"minute", 'timestring':"%Y/%m/%d/%H/%M"},
        {'subunit':4, 'id':"hour", 'timestring':"%Y/%m/%d/%H"},
        {'subunit':3, 'id':"day", 'timestring':"%Y/%m/%d"},
        {'subunit':2, 'id':"month", 'timestring':"%Y/%m"}
    ]
    categories=[
        "usage_total_low",
        "usage_total_high"
    ]

    for item in timeset:

        t = time.localtime(time.time())

        subunit = t[ item['subunit'] ]
        if (item['id']=='minute'): subunit = 0

        seconds = t[ 5 ]

        if subunit == 0 and seconds < 10:

            print 'new', item['id']
            for cat in categories:

                current = values[cat]

                try:
                    last = previous[cat][ item['id'] ]
                    value = float(current) - float(last)
                    localtime = time.strftime(item['timestring'], time.localtime())

                    # store value in db
                    db.Put("%s/%s"%(cat, localtime), str(value) )
                except:
                    previous[cat][ item['id'] ] = current
                    print "no previous available yet"






def background_thread():
    """Example of how to send server generated events to clients."""
    # ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=5)
    ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=20)

    # create database
    global db
    db = leveldb.LevelDB('./db')

    last_save = 0


    # wiat a bit
    time.sleep(4)

    count = 0

    while True:

        # read 811 chars or flush after timeout
        text = ser.read(811);

        ser.flush();

        # print "len: " +str(len(text))

        if len(text) == 811:

            # print text

            # try to find codes in text and get values
            response = {}
            for item in codes:
                match = re.search(item['code']+".*\(([0-9.]+)\*", text)
                if match:
                    value = match.group(1)
                    print item['id'] + " - " + value;
                    db.Put('last/%s'%item['id'], value);

                    response[ item['id'] ] = value;
                else:
                    print item['id'] + " no value found"

            storeValues(response);

            socketio.emit('my response', {
                'data': response,
                'count': len(response)
            },namespace='/test')
        else:
            print 'incomplete'
            print text


@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('my event', namespace='/test')
def test_message(message):
    print 'my event' + message

    global db

    usage_low = {}
    usage_high = {}
    for item in db.RangeIter(key_from = 'usage_low', key_to = 'usage_low~'):
        usage_low[item[0]] = item[1];

    for item in db.RangeIter(key_from = 'usage_high', key_to = 'usage_high~'):
        usage_high[item[0]] = item[1];

    emit('my response2',
            {'data': {'usage_low':usage_low, 'usage_high':usage_high}})

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
    print "connected"
    global db

    response = {'usage_total_low':0,
                'usage_total_high':0,
                'returned_total_low':0,
                'usage_current':0,
                'returned_total_high':0,
                'usage_total_gas':0,
                'returned_current':0}

    for item in db.RangeIter(key_from = 'last', key_to = 'last~'):
        print item
        response[item[0]] = item[1]

    emit('my response',
            {'data': response})


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
