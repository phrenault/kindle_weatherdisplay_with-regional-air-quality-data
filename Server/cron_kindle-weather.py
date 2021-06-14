#!/usr/bin/python3

#######################################################
### Autor: Nico Hartung <nicohartung1@googlemail.com> #
### Modified by: Philippe Renault, Date: 20.08.2020   #
### Improvements:									  #
### - adapted for Synology NAS with pyMySQL, Python3  #
### - modified to use SvgLib+ReportLab to create PNG  #
### - split and simplification of SQL data table      # 
### - further paramterisation of script               # 
### - bugfix for undefined variable "timestamp"       #
### - compatible with Kindle PaperWhite 2 (758 x 1024)#
###   and Kindle Touch (600 x 800)                    #
### - added Germany UBA air quality station data      #
### - Changed SVG Font to Helvetica                   #
###													  #
### ToDo: hardcoded for 3 devices only +no air quality#
###       hardcoded humidity value for device WHZ     #
#######################################################

# Weather Underground API Changes, see:
# https://apicommunity.wunderground.com/weatherapi/topics/weather-underground-api-changes

##########################
# Load necessary libraries
import os
import logging
#import time
#import datetime
from datetime import datetime, date, time
import locale
import codecs
import urllib.request
import json
import untangle # this library needs to be installed separately on Synology NAS
import pymysql # this library needs to be installed separately on Synology NAS: via SSH with 'pip3 install pymysql'
from svglib.svglib import svg2rlg # this library needs to be installed separately on Synology NAS: via SSH with 'pip3 install svglib' 
from reportlab.graphics import renderPM # this library is automatically installed when installing svglib
from PIL import Image # this library is automatically installed when installing svglib 
# To use DejaVuSans Font specified in SVG, install .TTF file in: /volume1/@appstore/py3k/usr/local/lib/python3.8/site-packages/reportlab/fonts/ via SSH. Also chmod 644 DejaVuSans.ttf
# As the folder font couldn't be found anymore after DS update, switched to use Helvetica font instead in SVG file
from get_uba_airquality import get_uba_airquality # Include Air Quality code

####################
# German time format
locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")

#########################
# Definition of variables
WEATHER_URL = "https://api.darksky.net/forecast"
###################################################################################################
# UserInput (replace ... with your own info):
WEATHER_KEY = "..."	# Get your own secret key by free registration at darksyky.net!
CITY = "..."
LATITUDE = "..."
LONGTITUDE = "..."

PATH = "/volume1/web/kindleweatherdisplay" # Path to all files necessary for the script, placed in new folder "kindleweatherdisplay"
LOG = "log/cron_kindle-weather.log"	# Create empty file in sub-directoy on server with this name
SVG_FILE = "%s/cron_kindle_PW2-weather_preprocess.svg" % PATH  # using SVG for Kindle Paper White2 Screen size
SVG_FILE2 = "%s/cron_kindle_touch-weather_preprocess.svg" % PATH # using SVG for Kindle Touch Screen size
SVG_OUTPUT = "%s/cron_kindle-weather_output.svg" % PATH
TMP_OUTPUT = "%s/cron_kindle-weather_tmp.png" % PATH

HOMEMATICIP = "192.168.178.X"	# IP of Homematic CCU
DEVICES = [...,...,...]		# DeviceID for Garten (Wettersensor), Wohnzimmer (Temp), DG-Whz (Temp); Pay attention to order, Max 3!
								# See "http://{YOUR-HOMEMATICIP}/addons/xmlapi/state.cgi?device_id={DEVICE}"
ROOMS = ["Wohnzimmer", "DG-Whz"]	# Order corresponding to device #2 and #3 (Max 2!)

SQLHOST = "localhost"
SQLPORT = 3307				# Port must be specified as number not string
SQLUSER = "..."
SQLPW = "..."
SQLDB = "homematic_data"	# Name of database with the following two tables
SQLTAB = "SENSOR_DATA"		# Table with sensor data in three rows: SENSOR, VALUE, DATETIME
SQLTAB2 = "HMIP_SENSORS"    # Optional: Table with overview of associated meta-data in rows: RAUM, ID, BEZEICHNUNG, SENSORART, SHORTFORM, EINHEIT

LogWrt=0	# Deactivate logging =0, to activate =1. Caution, file increases contineously!
# End of UserInput
###################################################################################################


#################
# Logging
logging.basicConfig(
	 filename=PATH + '/' + LOG,
	 level=logging.INFO,
	 #level=logging.WARNING,
	 format= '[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s',
	 #datefmt='%H:%M:%S'
)
console = logging.StreamHandler()
console.setLevel(logging.ERROR)
logging.getLogger('').addHandler(console)
logger = logging.getLogger(__name__)
if LogWrt==1:
	logging.info("SCRIPT START")


######################
# Functions definition
def _exec(cmd):
	rc = os.system(cmd)
	if (rc != 0):
		print("`%s` failed with error %d" % (cmd, rc))
		exit(rc)

def asInteger(output, id, data, addi):
	output = output.replace(id, str('%.0f%s' % (float(data), addi)))
	return(output)

def asIntegerTenOrMinusTen(output, id, data, addi):
	if float(data) <= -10 or float(data) >= 10:
		output = output.replace(id, str('%.0f%s' % (float(data), addi)))
	else:
		output = output.replace(id, str('%s%s' % (data, addi)))
	return(output)

def replace_daily(output, id, dataday, dataicon, datalow, datahigh, datawind, datarain, datarainint):
	output = output.replace("$D" + id, str(dataday + "."))
	output = output.replace("$I" + id, str(dataicon))
	output = output.replace("$L" + id, str('%.0f%s' % (float(datalow), "°")))
	output = output.replace("$H" + id, str('%.0f%s' % (float(datahigh), "°")))
	output = output.replace("$W" + id, str('%.0f' % (float(datawind))))
	#output = output.replace("$P" + id, str('%.2d' % (float(datarain))))
	output = output.replace("$P" + id, str('%.0f' % (float(datarain))))
	output = output.replace("$M" + id, str('%.1f' % (float(datarainint))))
	return(output)

def replace_hourly(output, id, datatime, dataicon, datarain, datatemp):
	output = output.replace("$K" + id, str(datatime))
	output = output.replace("$J" + id, str(dataicon))
	output = output.replace("$T" + id, str('%.0f%s' % (float(datatemp), "°")))
	if datarain >= 30 or dataicon == "rain":
		output = output.replace("$R" + id, str('%.0f%s' % (float(datarain), "%")))
	else:
		output = output.replace("$R" + id, str(""))
	return(output)

def sqlinsert(cursor, DEVICE, datapoint, datapointid, value):
	#timestamp = datetime.datetime.now().strftime("%Y.%m.%d %H:%M") #Datum und Uhrzeit im Format JJJJ.MM.TT HH:MM
	sql_query = "INSERT INTO %s (sensor, value, datetime) VALUES ('%s', '%s', CURRENT_TIMESTAMP)" % (SQLTAB, datapointid, value)
	cursor.execute(sql_query)
	db.commit()

def sqlminmax(cursor, datapointid, sort, decimal): # Return formatted Min or Max value of a list with specified decimals 
	sql_query = "SELECT value FROM %s WHERE sensor = %s AND DATE(datetime) = DATE(NOW()) ORDER BY value + 0 %s LIMIT 1" % (SQLTAB, datapointid, sort)
	cursor.execute(sql_query)
	for select in cursor.fetchall():
		#return('%.%sf' % (float(select[0]), decimal))
		return('%.{0}f'.format(decimal) % select["value"]) # SQL row labeled with "value" in table "sensor_data"
		#return('{}:.{}f'.format(select["value"], decimal)) 

def time_in_range(start, end, x):
    #Return true if x is in the range [start, end]
    #Usage: >>> starttime = datetime.time(23, 0, 0)
    #       >>> endtime = datetime.time(1, 0, 0)
    #       >>> time_in_range(starttime, endtime, datetime.time(23, 30, 0))
    if start <= end:
        return start <= x <= end
    else: #Over midnight
        return start <= x or x <= end

#####################
# API-Query
# https://api.darksky.net/forecast/...yourkey../..yourlat...,...yourlong...?&units=ca&lang=de
tries = 0
max_tries = 5
while tries < max_tries:
	try:
		apidata = urllib.request.urlopen(
			"%s/%s/%s,%s?&units=ca&lang=de" %
			(WEATHER_URL, WEATHER_KEY, LATITUDE, LONGTITUDE))
		json_apidata = apidata.read().decode('utf-8')
		parsed_apidata = json.loads(json_apidata)
		if LogWrt==1:
			logging.info("OK | dark sky api quest successfully")


		# Now
		weatherdata_now_text = parsed_apidata['currently']['summary'][:20] + (parsed_apidata['currently']['summary'][20:] and '...')
		weatherdata_now_icon = parsed_apidata['currently']['icon']
		if LogWrt==1:
			logging.info("- weatherdata_now | summary: %s" % (weatherdata_now_text.encode('utf-8')))
			logging.info("- weatherdata_now | icon: %s" % (weatherdata_now_icon))


		# Astronomie
		astronomy_today_sunrise = datetime.fromtimestamp(int(parsed_apidata['daily']['data'][0]['sunriseTime'])).strftime("%H:%M")
		astronomy_today_sunset = datetime.fromtimestamp(int(parsed_apidata['daily']['data'][0]['sunsetTime'])).strftime("%H:%M")
		astronomy_today_moonphase = parsed_apidata['daily']['data'][0]['moonPhase']*100

		if float(astronomy_today_moonphase) <= 2 or float(astronomy_today_moonphase) >= 98:
			astronomy_today_moonphase_icon = "moon-0"
		if float(astronomy_today_moonphase) >= 3 and float(astronomy_today_moonphase) <= 17:
			astronomy_today_moonphase_icon = "moon-waxing-25"
		if float(astronomy_today_moonphase) >= 18 and float(astronomy_today_moonphase) <= 32:
			astronomy_today_moonphase_icon = "moon-waxing-50"
		if float(astronomy_today_moonphase) >= 33 and float(astronomy_today_moonphase) <= 47:
			astronomy_today_moonphase_icon = "moon-waxing-75"
		if float(astronomy_today_moonphase) >= 48 and float(astronomy_today_moonphase) <= 52:
			astronomy_today_moonphase_icon = "moon-100"
		if float(astronomy_today_moonphase) >= 53 and float(astronomy_today_moonphase) <= 67:
			astronomy_today_moonphase_icon = "moon-waning-75"
		if float(astronomy_today_moonphase) >= 68 and float(astronomy_today_moonphase) <= 82:
			astronomy_today_moonphase_icon = "moon-waning-50"
		if float(astronomy_today_moonphase) >= 83 and float(astronomy_today_moonphase) <= 97:
			astronomy_today_moonphase_icon = "moon-waning-25"

		if LogWrt==1:
			logging.info("- astronomy_today | sunrise: %s, sunset %s" % (astronomy_today_sunrise, astronomy_today_sunset))
			logging.info("- astronomy_today | moonphase_icon: %s, moonphase: %s%%" % (astronomy_today_moonphase_icon, astronomy_today_moonphase))


		# Forecast Daily
		weatherdata_forecast_date = []
		weatherdata_forecast_weekday = []
		weatherdata_forecast_icon = []
		weatherdata_forecast_temphigh = []
		weatherdata_forecast_templow = []
		weatherdata_forecast_wind = []
		weatherdata_forecast_rain = []
		weatherdata_forecast_rainint= []
		for i in range(0, 3):
			weatherdata_forecast_date.append(datetime.fromtimestamp(int(parsed_apidata['daily']['data'][i]['time'])).strftime("%d.%m."))
			weatherdata_forecast_weekday.append(datetime.fromtimestamp(int(parsed_apidata['daily']['data'][i]['time'])).strftime("%a"))
			weatherdata_forecast_icon.append(parsed_apidata['daily']['data'][i]['icon'])
			weatherdata_forecast_temphigh.append(parsed_apidata['daily']['data'][i]['temperatureHigh'])
			weatherdata_forecast_templow.append(parsed_apidata['daily']['data'][i]['temperatureLow'])
			weatherdata_forecast_wind.append(parsed_apidata['daily']['data'][i]['windGust'])
			weatherdata_forecast_rain.append(parsed_apidata['daily']['data'][i]['precipProbability']*100)
			weatherdata_forecast_rainint.append(parsed_apidata['daily']['data'][i]['precipIntensityMax'])
			if LogWrt==1:
				logging.info("- forecast_daily | today: %s, %s, icon: %s, high: %s, low: %s, wind: %s km/h, pop: %s%%, rain: %s mm" % (weatherdata_forecast_weekday[i], weatherdata_forecast_date[i], weatherdata_forecast_icon[i], weatherdata_forecast_temphigh[i], weatherdata_forecast_templow[i], weatherdata_forecast_wind[i], weatherdata_forecast_rain[i], weatherdata_forecast_rainint[i]))


		# Forecast Hourly
		weatherdata_hourly_time = []
		weatherdata_hourly_icon = []
		weatherdata_hourly_temp = []
		weatherdata_hourly_wind = []
		weatherdata_hourly_rain = []
		for i in range(0, 24):
			weatherdata_hourly_time.append(datetime.fromtimestamp(int(parsed_apidata['hourly']['data'][i]['time'])).strftime("%H"))
			weatherdata_hourly_icon.append(parsed_apidata['hourly']['data'][i]['icon'])
			weatherdata_hourly_temp.append(parsed_apidata['hourly']['data'][i]['temperature'])
			weatherdata_hourly_wind.append(parsed_apidata['hourly']['data'][i]['windGust'])
			weatherdata_hourly_rain.append(parsed_apidata['hourly']['data'][i]['precipProbability']*100)
			if LogWrt==1:
				logging.info("- weatherdata_hourly | hour: %s, icon: %s, temp: %s, wind: %s km/h, pop: %s%%" % (weatherdata_hourly_time[i], weatherdata_hourly_icon[i], weatherdata_hourly_temp[i], weatherdata_hourly_wind[i], weatherdata_hourly_rain[i]))

	except urllib.error.HTTPError as e:
		tries = tries + 1
		logging.warn("WARN | dark sky api quest not successfully - error <%s> on trial no %s" % (e.code, tries))
		time.sleep(10)
		continue

	else:
		break

else:
	logging.error("FAIL |  dark sky api quest failed")


################
# On Homematic CCU check your device IDs with:
# http://192.168.178.XXX/addons/xmlapi/state.cgi?device_id=xxx,xxxx,xxxx

db = pymysql.connect(
	host=SQLHOST,
	port=SQLPORT,
	user=SQLUSER, 
	password=SQLPW,
	db=SQLDB,
	charset='utf8mb4',
	cursorclass=pymysql.cursors.DictCursor)

cursor = db.cursor()

try:
	for DEVICE in DEVICES:

		deviceurl = "http://{}/addons/xmlapi/state.cgi?device_id={}".format(HOMEMATICIP, DEVICE)
		xmldoc = untangle.parse(deviceurl)
		for ITEMS in xmldoc.state.device.channel:
			if ITEMS.get_elements('datapoint'):
				for DATA in ITEMS.datapoint:
					datapointname = DATA['name']

					### Temperatur
					if datapointname.endswith('.ACTUAL_TEMPERATURE'):
						datapointid = DATA['ise_id']
						datapoint = DATA['name']
						value = DATA['value']

						sqlinsert(cursor, DEVICE, datapoint, datapointid, value)

						# Whz / Room1
						if DEVICE == DEVICES[1]:
							wzt = '%.1f' % float(value)
							wth = sqlminmax(cursor, datapointid, "DESC", 1)
							wtl = sqlminmax(cursor, datapointid, "ASC", 1)

						# DG-Whz / Room2
						if DEVICE == DEVICES[2]:
							bat = '%.1f' % float(value)
							bth = sqlminmax(cursor, datapointid, "DESC", 1)
							btl = sqlminmax(cursor, datapointid, "ASC", 1)

						# Garten / Garden
						if DEVICE == DEVICES[0]:
							gtt = '%.1f' % float(value)
							gth = sqlminmax(cursor, datapointid, "DESC", 1)
							gtl = sqlminmax(cursor, datapointid, "ASC", 1)

					### Luftfeuchtigkeit / Humidity
					if datapointname.endswith('.HUMIDITY'):
						datapointid = DATA['ise_id']
						datapoint = DATA['name']
						value = DATA['value']

						sqlinsert(cursor, DEVICE, datapoint, datapointid, value)

						# Whz / Room1
						if DEVICE == DEVICES[1]:
							wzh = '%.0f' % float(value)
							whh = sqlminmax(cursor, datapointid, "DESC", 0)
							whl = sqlminmax(cursor, datapointid, "ASC", 0)

						# DG-Whz / Room2
						if DEVICE == DEVICES[2]:
							bah = '%.0f' % float(value)
							bhh = sqlminmax(cursor, datapointid, "DESC", 0)
							bhl = sqlminmax(cursor, datapointid, "ASC", 0)

						# Garten / Garden
						if DEVICE == DEVICES[0]:
							gah = '%.0f' % float(value)
							ghh = sqlminmax(cursor, datapointid, "DESC", 0)
							ghl = sqlminmax(cursor, datapointid, "ASC", 0)

					### Niederschlagsmenge / rainfall amount 
					# Bem: Ohne "Reset" wird die Niederschlagsmenge immer zum letzten Wert addiert - wächst immer weiter an, wird nicht auf 0 gesetzt.
					if datapointname.endswith('.RAIN_COUNTER'):
						datapointid = DATA['ise_id']
						datapoint = DATA['name']
						value = DATA['value']

						sqlinsert(cursor, DEVICE, datapoint, datapointid, value)

						# Garten - Differenzwert zwischen jetzt und Tagesanfang ermitteln
						if DEVICE == DEVICES[0]:
							cursor.execute(
								"SELECT maxi-mini FROM (SELECT MIN(value) mini, MAX(value) maxi FROM (SELECT value FROM %s WHERE sensor = %s AND DATE(datetime) >= DATE(NOW()) - INTERVAL 1 DAY ) mm1) mm2" % (SQLTAB, datapointid))
							for select in cursor.fetchall():
								grr = '%.1f' % float(select["maxi-mini"])
								#grr = '{}:.1f'.format(select["maxi-mini"])

					### Windrichtung / Wind direction
					if datapointname.endswith('.WIND_DIR'):
						datapointid = DATA['ise_id']
						datapoint = DATA['name']
						value = DATA['value']

						sqlinsert(cursor, DEVICE, datapoint, datapointid, value)

						# Garten / Garden
						if DEVICE == DEVICES[0]:
							gwdtemp = '%.1f' % float(value)

							if 0 <= float(gwdtemp) <= 22.4:
								gwd = "N"
							elif 22.5 <= float(gwdtemp) <= 67.4:
								gwd = "NO"
							elif 67.5 <= float(gwdtemp) <= 112.4:
								gwd = "O"
							elif 112.5 <= float(gwdtemp) <= 157.4:
								gwd = "SO"
							elif 157.5 <= float(gwdtemp) <= 202.4:
								gwd = "S"
							elif 202.5 <= float(gwdtemp) <= 247.4:
								gwd = "SW"
							elif 247.5 <= float(gwdtemp) <= 292.4:
								gwd = "W"
							elif 292.5 <= float(gwdtemp) <= 337.4:
								gwd = "NW"
							elif 337.5 <= float(gwdtemp) <= 360:
								gwd = "N"

					### Windgeschwindigkeit / Wind speed
					if datapointname.endswith('.WIND_SPEED'):
						datapointid = DATA['ise_id']
						datapoint = DATA['name']
						value = DATA['value']

						sqlinsert(cursor, DEVICE, datapoint, datapointid, value)

						# Garten / Garden
						if DEVICE == DEVICES[0]:
							gws = '%.1f' % float(value)
							cursor.execute(
								"SELECT value FROM %s WHERE sensor = %s AND DATE(datetime) = DATE(NOW()) ORDER BY value + 0 DESC LIMIT 1" %
								(SQLTAB, datapointid))
							for select in cursor.fetchall():
								gwh = '%.0f' % float(select["value"])
								#gwh = '{}:.0f'.format(select["value"])
finally:
	db.close()

############################################################
# Read air quality data for Germany for given UBA stations
# See get_uba_airquality.py script for more information and parameter settings
# Only call function every 6 hours is sufficient for reliable floating average values

chkhour = [1, 4, 7, 10, 13, 16, 19, 22]
nowtime = datetime.today()
for hour in chkhour:
	if time_in_range(time(hour-1, 30, 0), time(hour, 30, 0), time(nowtime.hour,nowtime.minute)):
		ubadata, ubaidx = get_uba_airquality('write')
	else:
		ubadata, ubaidx = get_uba_airquality('read')

	if LogWrt==1:
		logging.info("%s %s" % (ubadata, ubaidx))
	
############################################################
# Read SVG, compile output, generate SVG and convert to PNG
# To reduce size of SVG and clean from unnecessary data, use:
### http://www.svgminify.com > then copy/paste "defs"

for ROOM in ROOMS:

	OUTPUT = "%s/weatherdata-%s.png" % (PATH, ROOM.lower())
	ROOM1 = "Innen (%s)" % (ROOM)
	
	if (ROOM == ROOMS[0]):   #"Wohnzimmer":
		output = codecs.open(SVG_FILE, "r", encoding="utf-8").read()
	elif (ROOM == ROOMS[1]):   #"DG-Whz":
		output = codecs.open(SVG_FILE2, "r", encoding="utf-8").read()
	else: 
		logging.error("FAIL | Room not defined, no SVG defined")

	output = output.replace("$TEXT", str(weatherdata_now_text))
	output = output.replace("$I0", str(weatherdata_now_icon))
	output = asInteger(output, "$CT", gtt, "°")
	output = output.replace("$CHH", str(gth + "°"))
	output = output.replace("$CHL", str(gtl + "°"))
	output = output.replace("$CL", str(gah + ""))
	output = output.replace("$CAH", str(ghh + ""))
	output = output.replace("$CAL", str(ghl + ""))
	output = asInteger(output, "$CW", gws, "")
	output = output.replace("$CD", str(gwd))
	output = output.replace("$CHW", str(gwh))
	output = output.replace("$CR", str(grr))
	output = output.replace("$sunrise", str(astronomy_today_sunrise))
	output = output.replace("$sunset", str(astronomy_today_sunset))
	output = output.replace("$MO", str('%.2d' % (float(astronomy_today_moonphase))))
	output = output.replace("$MI", str(astronomy_today_moonphase_icon))

	output = output.replace("$AQ", str("000"))		# Hardcoded for the moment (air quality = Luftqualität)
	output = output.replace("$QL", str("000"))		# Hardcoded for the moment
	output = output.replace("$QH", str("000"))		# Hardcoded for the moment

	output = output.replace("$IDX", str(ubaidx))		# Air quality index
	output = output.replace("$PM", str(ubadata['PM10']))	# PM10 
	output = output.replace("$O3", str(ubadata['O3']))		# O3
	output = output.replace("$NO", str(ubadata['NO2']))		# NO2
	output = output.replace("$SO", str("00"))				# SO2 - Hard coded, as not available for current location

	#output = output.replace("$TIME", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
	output = output.replace("$TIME", datetime.today().strftime("%Y-%m-%d %H:%M"))
	output = output.replace("$LOC", str(CITY))

	for i in range(0, 3):
		output = replace_daily(output, str(i+1), weatherdata_forecast_weekday[i], weatherdata_forecast_icon[i], weatherdata_forecast_templow[i], weatherdata_forecast_temphigh[i], weatherdata_forecast_wind[i], weatherdata_forecast_rain[i], weatherdata_forecast_rainint[i])

	for i in range(0, 24):
		output = replace_hourly(output, str(i+1).zfill(2), weatherdata_hourly_time[i], weatherdata_hourly_icon[i], weatherdata_hourly_rain[i], weatherdata_hourly_temp[i])
	
	if (ROOM == ROOMS[0]):		#"Wohnzimmer":
		#ROOM2 = " "
		output = output.replace("$ROOM1", str(ROOM1))
		#output = output.replace("$ROOM2", str(ROOM2))
		output = output.replace("$BT", str(wzt + "°"))
		output = output.replace("$BSL", str(wtl + "°"))
		output = output.replace("$BSH", str(wth + "°"))
		#output = asIntegerTenOrMinusTen(output, "$BSL", wtl, "°")
		#output = asIntegerTenOrMinusTen(output, "$BSH", wth, "°")
		wzh = "0" #hard coded as zero for the moment, as no sensor.
		whh = "0"
		whl = "0"
		output = output.replace("$BH", str(wzh + "")) 
		output = output.replace("$BBH", str(whh + ""))
		output = output.replace("$BBL", str(whl + ""))
		
	elif (ROOM == ROOMS[1]):		#"DG-Whz":
		#ROOM2 = " "
		output = output.replace("$ROOM1", str(ROOM1))
		#output = output.replace("$ROOM2", str(ROOM2))
		output = output.replace("$BT", str(bat + "°"))
		output = output.replace("$BSL", str(btl + "°"))
		output = output.replace("$BSH", str(bth + "°"))
		#output = asIntegerTenOrMinusTen(output, "$BSL", btl, "°")
		#output = asIntegerTenOrMinusTen(output, "$BSH", bth, "°")
		output = output.replace("$BH", str(bah + ""))
		output = output.replace("$BBH", str(bhh + ""))
		output = output.replace("$BBL", str(bhl + ""))
	
	else:
		logging.warn("WARN | Room not defined, no specific data replaced")

	codecs.open(SVG_OUTPUT, "w", encoding="utf-8").write(output)
	drawing = svg2rlg(SVG_OUTPUT)	# Convert SVG to regular expression
	renderPM.drawToFile(drawing, TMP_OUTPUT, fmt="PNG")	# Convert SVG to PNG
	png_8bit = Image.open(TMP_OUTPUT).convert(mode='L') # Kindle needs true 8-bit grayscale PNG, otherwise it is distorted
	png_8bit.save(TMP_OUTPUT, optimize=True)	# Compress PNG
	_exec("mv -f '%s' '%s'" % (TMP_OUTPUT, OUTPUT)) # Change filename
	_exec("rm -f '%s'" % SVG_OUTPUT)	# Remove temporary files

if LogWrt==1:
	logging.info("SCRIPT END\n")
