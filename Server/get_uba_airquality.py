#!/usr/bin/python3

def get_uba_airquality(state):
	#############################################################################
	# Skript zum Auslesen der UBA Luftqualitätsdaten							#
	# Autor: Philippe Renault													#
	# Datum: 28.05.2020 													 	#
	# Kommentare: Werte brauchen nur alle 6h ab Mitternacht abgefragt zu werden #
	# Anzupassen je nach Standort ist/sind die Stationsnummer(n)				#
	#############################################################################

	# Beispiel CSV vom UBA für zwei Stationen in der Nähe von Musterhausen
	#---------------------------------------------------------------------
	# Stationscode	Datum	Feinstaub (PM₁₀) stündlich gleitendes Tagesmittel in µg/m³	Ozon (O₃) Ein-Stunden-Mittelwert in µg/m³	Stickstoffdioxid (NO₂) Ein-Stunden-Mittelwert in µg/m³	Luftqualitätsindex
	# DENW074	'01.01.2020 01:00'	29	52	-	gut
	# DENW329	'01.01.2020 01:00'	16	-	9	sehr gut
	#
	# Einheiten: µg/m³
	# Grenzwerte: PM10 = 50, NO2 = 200, O3 = 120
	#
	# Quelle: Umweltbundesamt, https://www.umweltbundesamt.de/daten/luft/luftdaten/luftqualitaet. Alle Uhrzeiten sind in der jeweils zum Messzeitpunkt gültigen Zeit (MEZ bzw. MESZ) angegeben.

	# Luftqualitätsindex (Quelle: https://www.umweltbundesamt.de/berechnungsgrundlagen-luftqualitaetsindex)
	#-------------------
	# Der Index basiert auf der gesundheitlichen Bewertung von Ozon- und NO2- Stundenmittelwerten und stündlich gleitenden PM10-Tagesmittelwerten. Zur Indexberechnung muss mindestens einer dieser drei Schadstoffe an der Station gemessen werden.
	# Anhand der aktuellsten, stündlichen Werte einer Station werden die gemessenen Schadstoffe mit folgenden Schwellwerten kategorisiert. Der Schadstoff, der die schlechteste Luftqualität aufweist, bestimmt die Indexfarbe.
	# Farbe, Index,	Stundenmittel NO2 in μg/m³,	stündlich gleitendes Tagesmittel PM10 in μg/m³,	Stundenmittel O3 in μg/m³
	# Dunkelrot, sehr schlecht,	> 200,	> 100,	> 240
	# Rot, schlecht,	101-200,	51-100,	181-240
	# Gelb, mäßig,	41-100,	36-50,	121-180
	# Grün, gut,	21-40,	21-35,	61-120
	# Türkis, sehr gut,	0-20,	0-20,	0-60

	# Verhaltensempfehlungen:
	# sehr schlecht:	Negative gesundheitliche Auswirkungen können auftreten. Wer empfindlich ist oder vorgeschädigte Atemwege hat, sollte körperliche Anstrengungen im Freien vermeiden.
	# schlecht:	Bei empfindlichen Menschen können nachteilige gesundheitliche Wirkungen auftreten. Diese sollten körperlich anstrengende Tätigkeiten im Freien vermeiden. In Kombination mit weiteren Luftschadstoffen können auch weniger empfindliche Menschen auf die Luftbelastung reagieren.
	# mäßig:	Kurzfristige nachteilige Auswirkungen auf die Gesundheit sind unwahrscheinlich. Allerdings können Effekte durch Luftschadstoffkombinationen und bei langfristiger Einwirkung des Einzelstoffes nicht ausgeschlossen werden. Zusätzliche Reize, z.B. ausgelöst durch Pollenflug, können die Wirkung der Luftschadstoffe verstärken, so dass Effekte bei empfindlichen Personengruppen (z.B. Asthmatikern) wahrscheinlicher werden.
	# gut:	Genießen Sie Ihre Aktivitäten im Freien, gesundheitlich nachteilige Wirkungen sind nicht zu erwarten.
	# sehr gut:	Beste Voraussetzungen, um sich ausgiebig im Freien aufzuhalten.


	##############
	# Libraries
	import csv
	import codecs
	import io
	import urllib.request
	from datetime import datetime, time, timedelta
	import pymysql
	#import pprint

	###########
	# Variables
	stations = ['1372','1129'] # Jackerath, Niederzier

	minus2st = timedelta(hours=-2) # Data are updated only once the full hour, so go back to previous hour for request
	stunde = datetime.now() + minus2st
	stunde = stunde.strftime('%H')
	if datetime.now().strftime('%H') != '00': # Handle previous day due to -2 hours
		datum = datetime.now().strftime('%Y-%m-%d')
	else:
		datum = datetime.now() + timedelta(days=-1)
		datum = datum.strftime('%Y-%m-%d')
		stunde = '21'
		
	#SQL Database connection credentials
	SQLHOST = "localhost"
	SQLPORT = 3307				# Port must be specified as number not string	
	SQLUSER = "root"
	SQLPW = "43.gWkh!"
	SQLDB = "uba_data"			# Name of database with the following two tables
	SQLTAB = "STATION_DATA"		# Table with final station data in three rows: SCHADSTOFF, MESSWERT, DATETIME
	SQLTAB2 = "airqualityindex" # Table for lookup of description based on airqualityindex (LQI)


	############
	# Functions
	def sqlinsert(cursor, datapointid, value):
		sql_query = "INSERT INTO %s (schadstoff, messwert, datetime) VALUES ('%s', '%s', CURRENT_TIMESTAMP)" % (SQLTAB, datapointid, value)
		cursor.execute(sql_query)
		db.commit()
		
	def sqlseluba(cursor, datapointid): # Return last value of a list 
		sql_query = "SELECT `Messwert` FROM %s WHERE `Schadstoff` = '%s' AND DATE(`DateTime`) = DATE(NOW()) ORDER BY `DateTime` +0 DESC LIMIT 1" % (SQLTAB, datapointid)
		cursor.execute(sql_query)
		for select in cursor.fetchall():
			return('%d' % select["Messwert"])

	#####################
	db = pymysql.connect(
		host=SQLHOST,
		port=SQLPORT,
		user=SQLUSER, 
		password=SQLPW,
		db=SQLDB,
		charset='utf8mb4',
		cursorclass=pymysql.cursors.DictCursor)

	cursor = db.cursor()

	# Initalize data array
	DATA = {'PM10': 0, 
			'O3': 0,
			'NO2': 0,
			'LQI': 0}

	lqi_list = {1: 'sehr schlecht',
		2: 'schlecht',
		3: 'mäßig',
		4: 'gut',
		5: 'sehr gut',
		99: 'k.A.'}
		
	#####################
	if state == 'write':
		# CSV-request
		dict_list = []
		for station in stations:
			url = 'https://www.umweltbundesamt.de/api/air_data/v2/airquality/csv?date_from=' + datum + '&time_from=' + stunde + '&date_to=' + datum + '&time_to=' + stunde + '&station=' + station + '&lang=de'
			#url = 'https://www.umweltbundesamt.de/api/air_data/v2/measures/csv?date_from=' + datum + '&time_from=' + stunde + '&date_to=' + datum + '&time_to=' + stunde + '&' + station + '&lang=de'
			#print(url)

			tries = 0
			max_tries = 3
			while tries < max_tries:
				try:
					# Open URL and get content from csv file
					url_open = urllib.request.urlopen(url)
					csv_reader = csv.reader(codecs.iterdecode(url_open, 'utf-8'), delimiter=';', dialect='unix')

					line_count = 0
					
					for row in csv_reader:
						if line_count == 0:
							#print(f'Column names are: {", ".join(row)}')
							line_count += 1
						elif line_count == 1:
							dict_list.append(row)
							line_count += 1
						else:
							#print(f'\t Station:{row[Stationscode]}, Feinstaub (PM10) stündlich gleitendes Tagesmittel in µg/m³:{row[Feinstaub (PM10) stündlich gleitendes Tagesmittel in µg/m³]}, Ozon (O3) Ein-Stunden-Mittelwert in µg/m³:{row[Ozon (O3) Ein-Stunden-Mittelwert in µg/m³]}, Luftqualitätsindex: {row[Luftqualitätsindex]}.')
							#print(f'\t Station:{row[Stationscode]}, Schadstoff:{row[Schadstoff]}, Messwert:{row[Messwert]} {row[Einheit]}.')
							line_count += 1
					#print(f'Processed {line_count} lines.')
					#pprint.pprint(dict_list)

				except urllib.error.HTTPError as e:
					tries = tries + 1
					print("WARNING | UBA api request not successful - error <%s> on trial no %s" % (e.code, tries))
					time.sleep(10)
					continue
				else:
					break

		#####################
		# Evaluation air-quality index (LQI)
		# Max value of all considered stations is retained to set the value and air quality

		PM10 = max(dict_list[0][2],dict_list[1][2])
		O3 = max(dict_list[0][3],dict_list[1][3])
		NO2 = max(dict_list[0][4],dict_list[1][4])
		LQI = [dict_list[0][5],dict_list[1][5]]
		idx = 99
		for val in LQI:
			keys = [key for key, value in lqi_list.items() if value == val]
			idx = min(idx,keys[0])
		#print(f'Luftqualität: {lqi_list[idx]}')

		DATA = {'PM10': PM10, 
				'O3': O3,
				'NO2': NO2,
				'LQI': idx}

		#####################
		# Write data to SQL database
		try:
			for key in DATA:
				datapointid = key
				value = DATA[key]
				sqlinsert(cursor, datapointid, value)
		finally:
			db.close()

	elif state == 'read':
		#####################
		# Read last data from SQL database
		try:
			for key in DATA:
				datapointid = key
				DATA[key] = sqlseluba(cursor, str(datapointid))
				if DATA['LQI'] is None:
					idx = 99
				else:
					idx = int(DATA['LQI'])
		finally:
			db.close()

	return(DATA,lqi_list[idx])
