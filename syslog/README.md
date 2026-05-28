# Meraki Syslog Workaround

Debug line with all properties:
FROMHOST: 'brbsgawap201.barry-callebaut.com', fromhost-ip: '10.157.7.201', HOSTNAME: 'brbsgawap201.barry-callebaut.com', PRI: 134,
syslogtag '', programname: '', APP-NAME: '', PROCID: '-', MSGID: '-',
TIMESTAMP: 'May 26 10:00:58', STRUCTURED-DATA: '-',
msg: '1779789658.526524123 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.122:52087 dst=40.99.204.178:443 mac=58:6D:67:D7:0F:28 request: UNKNOWN https://outlook.office365.com/...'
escaped msg: '1779789658.526524123 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.122:52087 dst=40.99.204.178:443 mac=58:6D:67:D7:0F:28 request: UNKNOWN https://outlook.office365.com/...'
inputname: imudp rawmsg: '<134>1 1779789658.526524123 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.122:52087 dst=40.99.204.178:443 mac=58:6D:67:D7:0F:28 request: UNKNOWN https://outlook.office365.com/...'
$!:
$.:
$/:


FROMHOST: 'brbsgawap201.barry-callebaut.com', fromhost-ip: '10.157.7.201', HOSTNAME: 'brbsgawap201.barry-callebaut.com', PRI: 134,
syslogtag '', programname: '', APP-NAME: '', PROCID: '-', MSGID: '-',
TIMESTAMP: 'May 26 10:36:04', STRUCTURED-DATA: '-',
msg: '1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/...'
escaped msg: '1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/...'
inputname: imudp rawmsg: '<134>1 1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/...'
$!:
$.:
$/:

rawmsgs:

<134>1 1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/...

<134>1 1779357454.275254117 BEWILBCSW001_2_Basement_ events Port bounce requested: Ports 12 will be switched off for 5 seconds

echo -n '<134>1 1779357454.275254117 BEWILBCSW001_2_Basement_ events Port bounce requested: Ports 12 will be switched off for 5 seconds' | nc -u -w 1 syslog 514

echo -n '<134>1 1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/... felix3' | nc -u -w 1 syslog 514

1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.24#012#0124:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/... felix3



MERAKI CONF BACKUP


module(load="imudp")
 
template(name="MerakiFwd" type="string"

  string="<%PRI%>1 %timereported:::date-rfc3339% %fromhost-ip% meraki - - - %rawmsg%\n")
 
template(name="ForwardWithSourceIP" type="string"

  string="<%PRI%>1 %TIMESTAMP:::date-rfc3339% %HOSTNAME% %APP-NAME% %PROCID% %MSGID% [origin ip=\"%fromhost-ip%\"] %msg%\n"

)
 
ruleset(name="forwardToAlloy") {

  *.* /var/log/syslog-raw;RSYSLOG_DebugFormat

  action(

    type="omfwd"

    protocol="tcp"

    target="127.0.0.1"

    port="1514"

   # template="ForwardWithSourceIP"

    TCP_Framing="octet-counted"

    KeepAlive="on"

  )

  stop

}
 
input(type="imudp" port="10514" ruleset="forwardToAlloy")
 
 

module(load="imudp")

# A completely transparent template that bypasses strict RFC 5424 header generation
template(name="ForwardToAlloyRaw" type="string"
  string="%rawmsg% origin_ip=\"%fromhost-ip%\"\n"
)

ruleset(name="forwardToAlloy") {
  action(
    type="omfwd"
    protocol="tcp"
    target="127.0.0.1"
    port="1514"
    template="ForwardToAlloyRaw"
    TCP_Framing="line-oriented" # Changed from octet-counted to standard line breaks
    KeepAlive="on"
  )
  stop
}

input(type="imudp" port="10514" ruleset="forwardToAlloy")




Terminology

BRBSGAWAP201_Farme_Service_


BR Brasil
BS Buying Station / region specific term
GA Gandu Site Name
WAP Wireless Access Point / Device Type
201 Device number

_Farme_Service_ unknown

