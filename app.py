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
import ast

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
                    db.Put("%s/%s/%s"%(cat, item['id'], localtime ), str(value) )
                except:
                    previous[cat][ item['id'] ] = current
                    print "no previous available yet"






def background_thread():
    # create database
    global db
    db = leveldb.LevelDB('./db')

    try:
        """Example of how to send server generated events to clients."""
        # ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=5)
        ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=20)

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

                socketio.emit('dataBroadcast', {
                    'data': response
                },namespace='/test')

            else:
                print 'incomplete'
                print text
    except:
        print "no serial port found"


@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('dataRequest', namespace='/test')
def test_message(message):
    print 'dataRequest', message

    start = message['data']['start']
    end = message['data']['end']
    id = message['data']['id']

    global db

    usage_low = {}
    usage_high = {}
    for item in db.RangeIter(key_from = 'usage_low/%s/%s'%(id,start), key_to = 'usage_low/%s/%s'%(id,end)):
        usage_low[item[0]] = item[1];

    for item in db.RangeIter(key_from = 'usage_high/%s/%s'%(id,start), key_to = 'usage_high/%s/%s'%(id,end)):
        key = item[0].split('/')[-1]
        usage_high[item[0]] = item[1];

    emit('my response2',
            {'data': {'usage_low':usage_low, 'usage_high':usage_high}})


@socketio.on('clearDataBase', namespace='/test')
def test_message():
    print 'clear DB'

    global db

    for item in db.RangeIter(key_from = '', key_to = '~'):
        print item[0];
        db.Delete( item[0] );

@socketio.on('fillDataBase', namespace='/test')
def test_message(message):
    print 'fill DB', message['data']

    data = ast.literal_eval(message['data'])
    global db

    count = 0
    for item in data:
        # print item, data[item]
        db.Put(item, data[item]);
        count = count + 1

    emit('response',
        {'data': "filled db with: " + str(count) + " elements"})


@socketio.on('dumpDataBase', namespace='/test')
def test_dump():
    print 'dump DB'

    global db

    for item in db.RangeIter(key_from = '', key_to = '~'):
        print item[0], item[1];
        emit('response',
            {'data': item[0] + " : " + item[1]})



@socketio.on('connect', namespace='/test')
def test_connect():
    print "connected"
    global db

    response = {}
    for item in db.RangeIter(key_from = 'last', key_to = 'last~'):
        key = item[0].split('/')[-1]
        response[key] = item[1]

    emit('my response',
            {'data': response})


@socketio.on('disconnect', namespace='/test')
def test_disconnect():
    print('Client disconnected', request.sid)


if __name__ == '__main__':
    # global thread
    if thread is None:
        thread = Thread(target=background_thread)
        thread.daemon = True
        thread.start()

    socketio.run(app, host='0.0.0.0', debug=True)
