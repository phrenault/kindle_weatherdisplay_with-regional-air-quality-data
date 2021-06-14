#!/bin/sh

################################################################
### Original Autor: Nico Hartung							   #
### Modified by: Philippe Renault, Date: 16.09.2019            #
###				 Adjustments, 24.02.2020 added SynoChat for msg#
###				 15.9.2020 added WAKEUPMODE for Kindle K4      #
################################################################

###########
### Install of this script on Kindle device:
## mkdir /mnt/us/scripts
## chmod 700 /mnt/us/scripts/weatherscript.sh
## mntroot rw
## cp /mnt/us/scripts/weather.conf /etc/upstart/
###########
### Important Info: 
# Wenn mehr Zeit in der üblichen Kindle-UI benötigt oder dauerhaft abgestellt werden soll: Kindle neu starten - ca. 20-30
# Sekunden Powertaste drücken. Wenn auf dem Boot-Screen, im Fortschrittsbalken, noch ca. 1 cm fehlen, kann man per SSH
# auf das Kindle zugreifen und mit "kill -9 -1" alle Prozesse zu beenden bzw. den sleep und das weatherscript.sh
# beenden oder die Upstart-Datei /etc/upstart/wetter.conf löschen und so den Autostart zukünftig verhindern. 
# SCHNELL, MAN HAT NUR 60 SEKUNDEN ZEIT!


###########
# Variables
NAME=weatherscript
SCRIPTDIR="/mnt/us/scripts"				# Path to PNG files on Kindle (see Install above)
LOG="${SCRIPTDIR}/${NAME}.log"
SUSPENDFOR=900                          # Default, flexible by F5INTWORKDAY and F5INTWEEKEND, 
NET="wlan0"

# rtc wakeup depends on kindle version
#WAKEUPMODE=0 # use /sys/class/rtc/rtc0/wakealarm
WAKEUPMODE=1 # use /sys/devices/platform/mxc_rtc.0/wakeup_enable (e.g. on K4 Kindle B0023)

LIMG="${SCRIPTDIR}/weatherdata.png"
LIMGBATT="${SCRIPTDIR}/weatherbattery.png"
LIMGERR="${SCRIPTDIR}/weathererror_image.png"
LIMGERRWLAN="${SCRIPTDIR}/weathererror_wlan.png"
LIMGERRNET="${SCRIPTDIR}/weathererror_network.png"
LIMGERRHOST="${SCRIPTDIR}/weathererror_hostname.png"

###########
# UserInput: IP and folder paths of application server to grab the data from
RSRV="192.168.178.X"				# IP of Synology NAS
RFLD="kindleweatherdisplay"			# foldername with path for files on the server
RSH="${RSRV}/${RFLD}/${NAME}.sh"	# path to server where to check for new weatherscript.sh file to download to Kindle
RPATH="${RSRV}/${RFLD}/log" #"/var/www/html/kindle-weather"	# path to server where to upload log files from Kindle by SSH

ROUTERIP="192.168.178.1"		 # Workaround, forget default gateway after STR

KINDLEDEVICES="\
192.168.178.XX|kindle-kt3-6gen-paperwhite2|wohnzimmer
192.168.178.XX|kindle-kt3-4gen-touch|dg-whz"
# IP, Hostname, Room (check router configuration, fix assigned IP is a must!)

# End of UserInput - Only modify SYNOMSGURL below if MSGACTIVE is needed
###########

F5INTWORKDAY="\
06,07,08,14,15,16,17,18|900
09,10,11,12,13,19,20|1800 
21,22,23|3600
00,01,02,03,04,05|21600"                # Refresh interval for workdays (900 sec = 15 min, 1800 sec = 30 min, etc.)
										# My router: Timer WLAN off between 0:00 - 6:00 o'clock. Thus, large interval.

F5INTWEEKEND="\
07,08,09,15,16,17,18,19|900
05,06,10,11,12,13,14,20,21|1800
22,23,00,01,02,03,04|3600"              # Refresh interval for weekends = 57 Refreshes per weekend day

###########
# Notification/SMS feature if available and necessary
MSGACTIV=1
# SMS via PlaySMS software on Linux based server (see https://playsms.org/)
#PLAYSMSUSER="admin"
#PLAYSMSPW="XXX"
#PLAYSMSURL="http://192.168.178.XX/playsms/index.php"
#
#CONTACTPAGERS="\
#0049123456789|Person1
#0049987654321|Person2"

# Notification via Synology NAS ChatBot (see https://www.synology.com/en-global/knowledgebase/DSM/help/Chat/chat_desc)
SYNOMSGUSER="admin"
SYNOMSGPW="XXX"
SYNOMSGURL="https://${RSRV}:5001/webapi/entry.cgi?api=SYNO.Chat.External&method=incoming&version=2&token=%22XXX%22&payload={%22text%22:%22KindleWeatherDisplay${MSGTEXT}%22}"

CONTACTPAGERS="\
SynologyNAS"

##############
### Functions
kill_kindle() {
  initctl stop framework    > /dev/null 2>&1      # "powerd_test -p" does not work, other command found
  initctl stop cmd          > /dev/null 2>&1
  initctl stop phd          > /dev/null 2>&1
  initctl stop volumd       > /dev/null 2>&1
  initctl stop tmd          > /dev/null 2>&1
  initctl stop webreader    > /dev/null 2>&1
  killall lipc-wait-event   > /dev/null 2>&1
  #initctl stop powerd      > /dev/null 2>&1      # battery state does not work
  #initctl stop lab126      > /dev/null 2>&1      # wlan interface does not work
  #initctl stop browserd    > /dev/null 2>&1      # not exist 5.9.4
  #initctl stop pmond       > /dev/null 2>&1      # not exist 5.9.4
}

customize_kindle() {
  mkdir /mnt/us/update.bin.tmp.partial 			  # no auto update from kindle firmware, new way at 5.12 and above - https://www.mobileread.com/forums/showthread.php?t=327879 & https://www.mobileread.com/forums/showpost.php?p=4037105&postcount=19
  touch /mnt/us/WIFI_NO_NET_PROBE				  # no wlan test for internet
}

debug_network() {
    echo "" >> ${LOG} 2>&1
    echo "" >> ${LOG} 2>&1
    echo "## DEBUG BEGIN" >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG ifconfig > `ifconfig ${NET}`" >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG wifid cmState > `lipc-get-prop com.lab126.wifid cmState`" >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG wifid signalStrength > `lipc-get-prop com.lab126.wifid signalStrength`" >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG wpa_cli status > `wpa_cli status verbose`" >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG ping ${ROUTERIP} > `ping ${ROUTERIP} -c4`" >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG ping ${RSRV} > `ping ${RSRV} -c4`" >> ${LOG} 2>&1
    echo "## DEBUG END" >> ${LOG} 2>&1
    echo "" >> ${LOG} 2>&1
    echo "" >> ${LOG} 2>&1
}

wait_wlan() {
  return `lipc-get-prop com.lab126.wifid cmState | grep CONNECTED | wc -l`
}

send_sms () {		# See https://playsms.org/
  for LINE in ${CONTACTPAGERS}; do
    CONTACTPAGER=`echo ${LINE} | awk -F\| '{print $1}'`
    CONTACTPAGERNAME=`echo ${LINE} | awk -F\| '{print $2}'`

    SMSTEXT=`echo ${MESSAGE} | sed 's/ /%20/g'`
    curl --silent "${PLAYSMSURL}?app=ws&u=${PLAYSMSUSER}&h=${PLAYSMSPW}&op=pv&to=${CONTACTPAGER}&msg=${SMSTEXT}" > /dev/null
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Nachricht an ${CONTACTPAGERNAME} versendet!" >> ${LOG} 2>&1
  done
}

send_msg () {		# Send message via Synology NAS ChatBot
  for LINE in ${CONTACTPAGERS}; do
    CONTACTPAGERNAME=`echo ${LINE} | awk '{print $1}'`

    MSGTEXT=`echo ${MESSAGE} | sed 's/ /%20/g'`
    #...${SYNOMSGUSER}...${SYNOSMGPW}...${CONTACTPAGERNAME}&msg=${MSGTEXT}
    curl --silent "${SYNOMSGURL}" > /dev/null
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Nachricht an ${CONTACTPAGERNAME} versendet!" >> ${LOG} 2>&1
  done
}

map_ip_hostname () {
	IPOK=0
	IP=`ifconfig ${NET} | grep "inet addr" | cut -d':' -f2 | awk '{print $1}'`
	#HOSTNAME=`nslookup ${IP} | grep Address | grep ${IP} | awk '{print $4}' | awk -F. '{print $1}'`
	for LINE in ${KINDLEDEVICES}; do	# find current Kindle via IP and allocate corresponding hostname
	if [ ${IPOK} == 0 ]; then
		KINDLEDEVICEIP=`echo ${LINE} | awk -F\| '{print $1}'`
		KINDLEDEVICE=`echo ${LINE} | awk -F\| '{print $2}'`
		KINDLEDEVICEROOM=`echo ${LINE} | awk -F\| '{print $3}'`
		if [ ${IP} == ${KINDLEDEVICEIP} ]; then
		  IPOK=1	# successful mapping, stop searching
		  HOSTNAME=${KINDLEDEVICE}
		  ROOM=${KINDLEDEVICEROOM}
		  IO_DP_BATTERY=`gasgauge-info -s | tr -d '%'`
		else
		  HOSTNAME="failed_map_ip_hostname"
		  eips -f -g "${LIMGERRHOST}"
		  echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Mappging der IP zum HOSTNAME fehlgeschlagen." >> ${LOG} 2>&1
		  #echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG WLAN cmState > `lipc-get-prop com.lab126.wifid cmState`" >> ${LOG} 2>&1
		  #echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG WLAN signalStrength > `lipc-get-prop com.lab126.wifid signalStrength`" >> ${LOG} 2>&1
		  #echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | DEBUG IP ifconfig > `ifconfig ${NET}`" >> ${LOG} 2>&1
		  debug_network
		fi
	fi
	done
}


##########
### Script

### Variables for IFs
NOTIFYBATTERY=0
REFRESHCOUNTER=0

### IP > HOSTNAME
map_ip_hostname

### Kill Kindle processes
kill_kindle

### Customize Kindle
customize_kindle

### Loop
while true; do

  ### Start
  echo "================================================" >> ${LOG} 2>&1

  ### Enable CPU Powersave
  CHECKCPUMODE=`cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor | grep -i "powersave" | wc -l`
  if [ ${CHECKCPUMODE} -eq 0 ]; then
    echo powersave > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | CPU runtergetaktet." >> ${LOG} 2>&1
  fi

  ### Disable Screensaver, no energy saving by powerd
  # powerd buggy since 5.4.5 - https://www.mobileread.com/forums/showthread.php?t=235821
  CHECKSAVER=`lipc-get-prop com.lab126.powerd status | grep -i "prevent_screen_saver:0" | wc -l`
  if [ ${CHECKSAVER} -eq 0 ]; then
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 >> ${LOG} 2>&1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Standard Energiesparmodus deaktiviert." >> ${LOG} 2>&1
  fi

  ### Check Battery State
  CHECKBATTERY=`gasgauge-info -s | tr -d '%'`
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Batteriezustand: ${CHECKBATTERY}%" >> ${LOG} 2>&1
  if [ ${CHECKBATTERY} -gt 80 ]; then
    NOTIFYBATTERY=0
  fi
  if [ ${CHECKBATTERY} -le 1 ]; then
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Batteriezustand 1%, statisches Batteriezustandsbild gesetzt, WLAN deaktivert, Ruhezustand!" >> ${LOG} 2>&1
    eips -f -g "${LIMGBATT}"
    lipc-set-prop com.lab126.wifid enable 0
	if [ $WAKEUPMODE == 0 ]; then
		echo 0 > /sys/class/rtc/rtc0/wakealarm
    else
		echo 0 > /sys/devices/platform/mxc_rtc.0/wakeup_enable
	fi
	echo "mem" > /sys/power/state
  fi

  ### Set SUSPENDFOR
  # no regex in if with /bin/sh
  DAYOFWEEK=`date +%u`  # 1=Monday
  HOURNOW=`date +%H`    # Hour
  # Workdays
  if [ ${DAYOFWEEK} -ge 1 ] && [ ${DAYOFWEEK} -le 5 ]; then
    for LINE in ${F5INTWORKDAY}; do
      HOURS=`echo ${LINE} | awk -F\| '{print $1}'`
      echo "${HOURS}" | grep ${HOURNOW} > /dev/null 2>&1
      if [ $? -eq 0 ]; then
        SUSPENDFOR=`echo ${LINE} | awk -F\| '{print $2}'`
        echo "${SUSPENDFOR}"
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Aufwachintervall für den nächsten Ruhezustand auf ${SUSPENDFOR} gesetzt." >> ${LOG} 2>&1
      fi
    done
  fi
  # Weekend
  if [ ${DAYOFWEEK} -ge 6 ] && [ ${DAYOFWEEK} -le 7 ]; then
    for LINE in ${F5INTWEEKEND}; do
      HOURS=`echo ${LINE} | awk -F\| '{print $1}'`
      echo "${HOURS}" | grep ${HOURNOW} > /dev/null 2>&1
      if [ $? -eq 0 ]; then
        SUSPENDFOR=`echo ${LINE} | awk -F\| '{print $2}'`
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Aufwachintervall für den nächsten Ruhezustand auf ${SUSPENDFOR} gesetzt." >> ${LOG} 2>&1
      fi
    done
  fi

  ### Calculation WAKEUPTIMER
  WAKEUPTIMER=$(( `date +%s` + ${SUSPENDFOR} ))
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Aufwachzeitpunkt für den nächsten Ruhezustand `date -d @${WAKEUPTIMER} '+%Y-%m-%d_%H:%M:%S'`." >> ${LOG} 2>&1

  ### Reassociate WLAN - 2020-11-09
  # https://www.mobileread.com/forums/showthread.php?t=312150
  wpa_cli -i wlan0 reassociate >> ${LOG} 2>&1
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN reassociate." >> ${LOG} 2>&1

  ### Wait on WLAN
  WLANNOTCONNECTED=0
  WLANCOUNTER=0
  while wait_wlan; do
    if [ ${WLANCOUNTER} -eq 10 ] || [ ${WLANCOUNTER} -eq 30 ] || [ ${WLANCOUNTER} -eq 50 ] || [ ${WLANCOUNTER} -eq 60 ]; then
      debug_network
    fi
    if [ ${WLANCOUNTER} -eq 10 ]; then
      wpa_cli -i wlan0 disconnect >> ${LOG} 2>&1
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN disconnect." >> ${LOG} 2>&1
      wpa_cli -i wlan0 reconnect >> ${LOG} 2>&1
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN reconnect." >> ${LOG} 2>&1
    fi
    if [ ${WLANCOUNTER} -eq 30 ]; then
      lipc-set-prop com.lab126.wifid enable 0 >> ${LOG} 2>&1
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN deaktivieren." >> ${LOG} 2>&1
      lipc-set-prop com.lab126.wifid enable 1 >> ${LOG} 2>&1
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN aktivieren." >> ${LOG} 2>&1
    fi
    if [ ${WLANCOUNTER} -eq 50 ]; then
        wpa_cli -i wlan0 reassociate >> ${LOG} 2>&1
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN reassociate." >> ${LOG} 2>&1
    fi
    if [ ${WLANCOUNTER} -eq 60 ]; then
	  eips -f -g "${LIMGERRWLAN}"
      WLANNOTCONNECTED=1
	  echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Leider keine erfolgreiche Verbindung mit einem WLAN hergestellt." >> ${LOG} 2>&1
      break
    fi
    let WLANCOUNTER=WLANCOUNTER+1
    echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Warte auf WLAN (Versuch ${WLANCOUNTER})." >> ${LOG} 2>&1
    sleep 1
  done

  ### Connected with WLAN?
  if [ ${WLANNOTCONNECTED} -eq 0 ]; then

    ### IP > HOSTNAME
    map_ip_hostname

    ### Workaround Default Gateway after STR
    GATEWAY=`ip route | grep default | grep ${NET} | awk '{print $3}'`
    if [ -z "${GATEWAY}" ]; then
      route add default gw ${ROUTERIP} >> ${LOG} 2>&1
    fi

	### Battery @ ioBroker
    #echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Batteriezustand an ioBroker soll übergeben werden!" >> ${LOG} 2>&1
    #curl --silent "http://${RSRV}:8087/set/${IO_DP_BATTERY}?value=${CHECKBATTERY}" --connect-timeout 2 > /dev/null 2>&1
    #echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Batteriezustand an ioBroker übergeben!" >> ${LOG} 2>&1

    ### Battery State critical? send message!
    if [ ${CHECKBATTERY} -le 5 ] && [ ${NOTIFYBATTERY} -eq 0 ]; then
      NOTIFYBATTERY=1
      if [ ${MSGACTIV} -eq 1 ]; then
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Batteriezustand kritisch, Nachrichten werden verschickt!" >> ${LOG} 2>&1
        MESSAGE="Der Batteriezustand von ${HOSTNAME} ist kritisch (${CHECKBATTERY}%) - bitte laden!"
        send_msg
      else
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Batteriezustand kritisch." >> ${LOG} 2>&1
      fi
    fi

    ### Check new Script
    # wget (-N) can't https
    RSTATUSSH=`curl --silent --head "http://${RSH}" --connect-timeout 2| head -n 1 | cut -d$' ' -f2`
    if [ ${RSTATUSSH} -eq 200 ]; then
      LMTIMESH=`stat -c %Y "${SCRIPTDIR}/${NAME}.sh"`
      curl --silent --time-cond "${SCRIPTDIR}/${NAME}.sh" --output "${SCRIPTDIR}/${NAME}.sh" "http://${RSH}"
      RMTIMESH=`stat -c %Y "${SCRIPTDIR}/${NAME}.sh"`
      if [ ${RMTIMESH} -gt ${LMTIMESH} ]; then
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Skript aktualisiert, Neustart durchführen." >> ${LOG} 2>&1
        chmod 777 "${SCRIPTDIR}/${NAME}.sh"
        reboot
        exit
      fi
    else
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Skript nicht gefunden (HTTP-Status ${RSTATUSSH})." >> ${LOG} 2>&1
    fi

    ### Get new Weather data (wget can't https)
	if [ ${HOSTNAME} != "failed_map_ip_hostname" ]; then
	RIMG="${RSRV}/${RFLD}/weatherdata-${ROOM}.png"
    let REFRESHCOUNTER=REFRESHCOUNTER+1
    RSTATUSIMG=`curl --silent --head "http://${RIMG}" --connect-timeout 2 | head -n 1 | cut -d$' ' -f2`
    if [ ${RSTATUSIMG} -eq 200 ]; then
      curl --silent --output "$LIMG" "http://${RIMG}" --connect-timeout 2
      if [ ${REFRESHCOUNTER} -le 5 ]; then    #if [ ${REFRESHCOUNTER} -ne 2 ]; then
        eips -g "$LIMG"
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Wetterbild aktualisiert." >> ${LOG} 2>&1
      else
        eips -f -g "$LIMG"
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Wetterbild und E-Ink aktualisiert." >> ${LOG} 2>&1
        REFRESHCOUNTER=0
      fi
    elif [ -z "${RSTATUSIMG}" ]; then
        eips -f -g "$LIMGERRNET"
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Webserver reagiert nicht. Webserver läuft? Server erreichbar? Kindle mit dem WLAN verbunden?" >> ${LOG} 2>&1
		debug_network
    else
        eips -f -g "$LIMGERR"
        echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Wetterbild auf Webserver nicht gefunden (HTTP-Status ${RSTATUSSH})." >> ${LOG} 2>&1
		debug_network
    fi
	else
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Hostname nicht bekannt, Wetterbild konnte nicht aktualisiert werden." >> ${LOG} 2>&1
      debug_network
    fi
  fi

    ### Copy log by ssh
    cat ${LOG} | ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  -o ConnectTimeout=1 -o ConnectionAttempts=1 -i /mnt/us/scripts/id_rsa_kindle -l kindle ${RSRV} "cat >> ${RPATH}/${NAME}_${HOSTNAME}.log" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
      rm ${LOG}
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Log per SSH an Remote-Server übergeben und lokal gelöscht." >> ${LOG} 2>&1
    else
      echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Log konnte nicht an den Remote-Server übergeben werden." >> ${LOG} 2>&1
    fi


  ### Disable WLAN
  # No stable "wakealarm" with enabled WLAN
  #lipc-set-prop com.lab126.cmd wirelessEnable 0 >> ${LOG} 2>&1
  #lipc-set-prop com.lab126.wifid enable 0 >> ${LOG} 2>&1
  #echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | WLAN deaktivieren." >> ${LOG} 2>&1

  ### Set wakealarm
  if [ $WAKEUPMODE == 0 ]; then 
    echo 0 > /sys/class/rtc/rtc0/wakealarm
    echo ${WAKEUPTIMER} > /sys/class/rtc/rtc0/wakealarm
  else
    echo 0 > /sys/devices/platform/mxc_rtc.0/wakeup_enable
    echo ${SUSPENDFOR} > /sys/devices/platform/mxc_rtc.0/wakeup_enable
  fi

  ### Go into Suspend to Memory (STR)
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | ${HOSTNAME} | Ruhezustand starten." >> ${LOG} 2>&1
  echo "mem" > /sys/power/state

done
