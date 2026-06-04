# Rsyslog - Syslog Preprocessing

Grafana Alloy provides a Syslog receiver which expects syslog messages to meet either x or y standards. A lot of devices, in particular networking devices do not meet these specifications and therefore it might be necessary to use Rsyslog as a preprocesser.

## Meraki Timestamp Workaround

While Meraki devices can forward Syslog messages, they use Epoch for their timestamps which is not inline with the standard and Alloy will drop these messages.
To fix this, Rsyslog will take the message and update / reformat the Syslog header to meet the official standard.

See [`rsyslog.conf`](./rsyslog.conf) for the configuration.

Also have a look at the [`config.alloy`](../alloy/config.alloy) syslog section.


### Sample Meraki Syslog Messages

You can send these raw Meraki Syslog messages via command line:

```shell
echo -n '<134>1 1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/...' | nc -u -w 1 syslog 514

echo -n '<134>1 1779357454.275254117 BEWILBCSW001_2_Basement_ events Port bounce requested: Ports 12 will be switched off for 5 seconds' | nc -u -w 1 syslog 514
```
