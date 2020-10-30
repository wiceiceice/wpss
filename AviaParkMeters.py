#!/usr/bin/python

"""
Muliple Read Property

This application has a static list of points that it would like to read.  It reads the
values of each of them continiously
"""

class mem: pass

from collections import deque
from datetime import datetime
import time
import threading

from bacpypes.debugging import bacpypes_debugging, ModuleLogger
from bacpypes.consolelogging import ConfigArgumentParser

from bacpypes.core import run, deferred
from bacpypes.task import RecurringTask

from bacpypes.pdu import Address
from bacpypes.app import LocalDeviceObject, BIPSimpleApplication
from bacpypes.object import get_datatype

from bacpypes.apdu import ReadPropertyRequest, Error, AbortPDU, ReadPropertyACK
from bacpypes.primitivedata import Unsigned
from bacpypes.constructeddata import Array
from bacpypes.basetypes import ServicesSupported


# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
this_device = None
this_application = None
this_console = None

mem.readings_from_counters = {}
mem.dict_counter_readings = {}
save_dict={}

mem.skip_first_save=1
mem.sayac_okuma_flag=1

# Create point list ###########################################################
from xlrd import open_workbook

book = open_workbook('C:/MeterDefinitions.xls')
sheet = book.sheet_by_index(0)

number_of_rows = sheet.nrows

point_list = []
dict_mako = {}
for row_index in xrange(1, number_of_rows):
    address=str(sheet.cell(row_index, 6).value)
    programid=str(int(sheet.cell(row_index, 0).value))
    object_instance = int(sheet.cell(row_index, 3).value)
    temp_list = []
    temp_list.append(address)
    temp_list.append('analogInput')
    temp_list.append(object_instance)
    temp_list.append("presentValue")
    temp_list.append(programid)
    point_list.append(temp_list)

    #create dict of dict of list to send to mako
    grs_key=sheet.cell(row_index, 5).value
    busbar_key=sheet.cell(row_index, 4).value

    if not grs_key in dict_mako:
        dict_mako[grs_key] = {}
    if not busbar_key in dict_mako[grs_key]:
        dict_mako[grs_key][busbar_key] = []
    dict_mako[grs_key][busbar_key].append(programid)
#
#   PrairieDog
#

@bacpypes_debugging
class PrairieDog(BIPSimpleApplication, RecurringTask):

    def __init__(self, interval, *args):
        if _debug: PrairieDog._debug("__init__ %r, %r", interval, args)
        BIPSimpleApplication.__init__(self, *args)
        RecurringTask.__init__(self, interval * 1000)

        # keep track of requests to line up responses
        self._request = None

        # start out idle
        self.is_busy = False
        self.point_queue = deque()
        self.response_values = []

        # install it
        self.install_task()

    def process_task(self):
        if _debug: PrairieDog._debug("process_task")
        global point_list

        # check to see if we're idle
        if self.is_busy:
            if _debug: PrairieDog._debug("    - busy")
            return

        # now we are busy
        self.is_busy = True
        mem.sayac_okuma_flag=1

        # turn the point list into a queue
        self.point_queue = deque(point_list)

        # clean out the list of the response values
        self.response_values = []

        # fire off the next request
        self.next_request()

    def next_request(self):
        if _debug: PrairieDog._debug("next_request")

        # check to see if we're done
        if not self.point_queue:
            if _debug: PrairieDog._debug("    - done")


            # dump out the results
            for request, response in zip(point_list, self.response_values):
                mem.readings_from_counters[request[4]]=response

            # no longer busy
            self.is_busy = False
            mem.sayac_okuma_flag=0

            return

        # get the next request
        addr, obj_type, obj_inst, prop_id, program_id = self.point_queue.popleft()

        # build a request
        self._request = ReadPropertyRequest(
            objectIdentifier=(obj_type, obj_inst),
            propertyIdentifier=prop_id,
            )
        self._request.pduDestination = Address(addr)
        if _debug: PrairieDog._debug("    - request: %r", self._request)

        # forward it along
        BIPSimpleApplication.request(self, self._request)

    def confirmation(self, apdu):
        if _debug: PrairieDog._debug("confirmation %r", apdu)

        if isinstance(apdu, Error):
            if _debug: PrairieDog._debug("    - error: %r", apdu)
            self.response_values.append(apdu)

        elif isinstance(apdu, AbortPDU):
            if _debug: PrairieDog._debug("    - abort: %r", apdu)
            self.response_values.append(apdu)

        elif (isinstance(self._request, ReadPropertyRequest)) and (isinstance(apdu, ReadPropertyACK)):
            # find the datatype
            datatype = get_datatype(apdu.objectIdentifier[0], apdu.propertyIdentifier)
            if _debug: PrairieDog._debug("    - datatype: %r", datatype)
            if not datatype:
                raise TypeError, "unknown datatype"

            # special case for array parts, others are managed by cast_out
            if issubclass(datatype, Array) and (apdu.propertyArrayIndex is not None):
                if apdu.propertyArrayIndex == 0:
                    value = apdu.propertyValue.cast_out(Unsigned)
                else:
                    value = apdu.propertyValue.cast_out(datatype.subtype)
            else:
                value = apdu.propertyValue.cast_out(datatype)
            if _debug: PrairieDog._debug("    - value: %r", value)

            # save the value
            self.response_values.append(value)

        # fire off another request
        deferred(self.next_request)


# DATABASE PARAMETERS ############################################################################

import sqlite3

sqlite_file = 'tenantdata.sqlite'    # name of the sqlite database file
table_name = 'tenant_counter'   # name of the table to be created
date_col = 'date' # name of the date column
time_col = 'time'# name of the time column
date_time_col = 'date_time' # name of the date & time column
id_col = 'id' # name of the id column
sayacdegeri_col = 'sayacdeger' # name of the counter value column

# COUNTER STORE VALUES ############################################################################

def sayac_yaz():

    threading.Timer(3600, sayac_yaz).start()

    if (mem.skip_first_save==1):
        mem.skip_first_save=0
        return

    print "Sayaclari kaydediyor"

    save_time = datetime.now()

    if mem.sayac_okuma_flag==0:
        save_dict=mem.readings_from_counters

    # Connecting to the database file
    conn2 = sqlite3.connect('tenantdata.sqlite')
    c2 = conn2.cursor()

    for idx in save_dict:
        sayac_value=save_dict[idx]
        actual_counter_id=idx
        if isinstance(sayac_value, float):
            # insert a new row with the current date and time, e.g., 2014-03-06
            c2.execute('''INSERT INTO tenant_counter VALUES(?,?,?,?,?)''' , (actual_counter_id, save_time.strftime('%Y-%m-%d'), save_time.strftime('%H:%M:%S'), save_time.strftime('%Y-%m-%d %H:%M:%S'), sayac_value))
        else:
            # insert a new row with the current date and time, e.g., 2014-03-06
            c2.execute('''INSERT INTO tenant_counter VALUES(?,?,?,?,?)''' , (actual_counter_id, save_time.strftime('%Y-%m-%d'), save_time.strftime('%H:%M:%S'), save_time.strftime('%Y-%m-%d %H:%M:%S'), 'Error!'))
    conn2.commit()
    conn2.close()
    return


# WEB APP ############################################################################

import cherrypy
import webbrowser
import os
import json
import sys

from mako.lookup import TemplateLookup
from mako.template import Template

path   = os.path.abspath(os.path.dirname(__file__))

MEDIA_DIR = os.path.join(path, "media")
VIEW_DIR  = os.path.join(path, "view")

data = json.load(open('media/data.json', 'r+'))

lookup = TemplateLookup(directories=[VIEW_DIR], output_encoding='utf-8', encoding_errors='replace')

conf = {'/media':
                {'tools.staticdir.on': True,
                 'tools.staticdir.dir': MEDIA_DIR,
                 'tools.encode.on' : True,
                 'tools.encode.encoding' : "utf8",
                },
           '/view':
                {'tools.staticdir.on': True,
                 'tools.staticdir.dir': VIEW_DIR,
                 'tools.encode.on' : True,
                 'tools.encode.encoding' : "utf8",
                }
        }

class AjaxApp(object):
    @cherrypy.expose
    def index(self):
        mydict = dict_mako
        template = lookup.get_template('index.html')
        return template.render(mydict=mydict)

    @cherrypy.expose
    def sayac_oku(self):

        if mem.sayac_okuma_flag==0:
            temp_dict={}
            temp_dict=mem.readings_from_counters
    
            for meterid in temp_dict:
                metervalue=mem.readings_from_counters[meterid]
                if isinstance(metervalue, float):
                    mem.dict_counter_readings[meterid] = "%.2f kwh" % (metervalue/1000)
                else:
                    mem.dict_counter_readings[meterid] = 'Error!'



        cherrypy.response.headers['Content-Type'] = 'application/json'
        cherrypy.response.headers['Expires'] = 'Sun, 19 Nov 1978 05:00:00 GMT'
        cherrypy.response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        cherrypy.response.headers['Pragma'] = 'no-cache'

        return json.dumps(mem.dict_counter_readings)

    @cherrypy.expose
    def submit(self, main_id, unitprice, val1, val2):

        # Connecting to the database file
        conn = sqlite3.connect(sqlite_file)
        c = conn.cursor()
        # Retrieve all IDs of entries between 2 date_times
        c.execute("SELECT {countervalue} FROM {tn} WHERE ({cn} = '{xn}') & ({idn} = '{sn}') ".\
        format(countervalue=sayacdegeri_col, tn=table_name, cn=date_col, xn=val1, idn=id_col, sn=main_id))

        readings_at_first_date=[]
        readings_at_first_date=c.fetchall()
        if not readings_at_first_date:
            first_index=[0.0,]
        else:
            first_index=max(readings_at_first_date)

        # if list is empty, give it 0 as default
        if first_index[0]=='Error!':
            first_index=[0.0,]

        conn.commit()
        c.execute("SELECT {countervalue} FROM {tn} WHERE ({cn} = '{xn}') & ({idn} = '{sn}') ".\
        format(countervalue=sayacdegeri_col, tn=table_name, cn=date_col, xn=val2, idn=id_col, sn=main_id))

        readings_at_last_date=[]
        readings_at_last_date=c.fetchall()
        if not readings_at_last_date:
            last_index=[0.0,]
        else:
            last_index=max(readings_at_last_date)

        # if list is empty, give it 0 as default
        if last_index[0]=='Error!':
            last_index=[0.0,]

        conn.commit()
        conn.close()

        difference=abs((first_index[0])-(last_index[0]))
        fatura= ((difference/1000) * int(unitprice))

        #kwh cinsinden degerleri hesapla ve gonder
        difference_str="%.2f kwh" % (difference/1000)
        first_index_str="%.2f kwh" % (first_index[0]/1000)
        last_index_str="%.2f kwh" % (last_index[0]/1000)

        r = {'1':first_index_str, '2': last_index_str, '3': difference_str, '4': str(fatura)}

        cherrypy.response.headers['Content-Type'] = 'application/json'
        cherrypy.response.headers['Expires'] = '0'
        cherrypy.response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        cherrypy.response.headers['Pragma'] = 'no-cache'

        return json.dumps(r)

    @cherrypy.expose
    def changeState(self,item1):
        data['unitprice']=item1

        json.dump(data, open('media/data.json', 'w'))

        cherrypy.response.headers['Content-Type'] = 'application/json'
        cherrypy.response.headers['Expires'] = 'Sun, 19 Nov 1978 05:00:00 GMT'
        cherrypy.response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        cherrypy.response.headers['Pragma'] = 'no-cache'


        return json.dumps(data)

    @cherrypy.expose
    def unitprice_init(self):

        cherrypy.response.headers['Content-Type'] = 'application/json'
        cherrypy.response.headers['Expires'] = 'Sun, 19 Nov 1978 05:00:00 GMT'
        cherrypy.response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        cherrypy.response.headers['Pragma'] = 'no-cache'


        return json.dumps(data)


def open_page():
    pass

cherrypy.engine.subscribe('start', open_page)
cherrypy.tree.mount(AjaxApp(), '/', config=conf)
cherrypy.engine.start()

# Start Recorder ###################################################################################################################################

sayac_yaz()

####################################################################################################################################################

#
#   __main__
#

try:
    # parse the command line arguments
    parser = ConfigArgumentParser(description=__doc__)

    # now parse the arguments
    args = parser.parse_args()

    if _debug: _log.debug("initialization")
    if _debug: _log.debug("    - args: %r", args)

    # make a device object
    this_device = LocalDeviceObject(
        objectName=args.ini.objectname,
        objectIdentifier=int(args.ini.objectidentifier),
        maxApduLengthAccepted=int(args.ini.maxapdulengthaccepted),
        segmentationSupported=args.ini.segmentationsupported,
        vendorIdentifier=int(args.ini.vendoridentifier),
        )

    # build a bit string that knows about the bit names
    pss = ServicesSupported()
    pss['whoIs'] = 1
    pss['iAm'] = 1
    pss['readProperty'] = 1
    pss['writeProperty'] = 1

    # set the property value to be just the bits
    this_device.protocolServicesSupported = pss.value

    # make a dog
    this_application = PrairieDog(240, this_device, args.ini.address)

    _log.debug("running")

    run()

except Exception, e:
    _log.exception("an error has occurred: %s", e)
finally:
    _log.debug("finally")
