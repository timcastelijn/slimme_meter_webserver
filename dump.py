

import time
from threading import Thread

import serial
import leveldb
import re

db = leveldb.LevelDB('./db')

for item in db.RangeIter(key_from = '', key_to = ''):
    print item
