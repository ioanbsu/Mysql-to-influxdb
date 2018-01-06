#!/usr/bin/python

import argparse
import logging
import time
from ConfigParser import RawConfigParser
from datetime import datetime

import MySQLdb
import MySQLdb.cursors
from influxdb import InfluxDBClient

logger = logging.getLogger(__name__)


class Mysql2Influx:

    def __init__(self,config):

        #TODO put site info into settings file
        self._table = config.get('mysql','table')

        if config.has_option('mysql','time_field'):
            self._time_field = config.get('mysql','time_field')
        else:
            self._time_field = 'timestamp'
        #intitialise client for mysql database
        self._mysql_host = config.get('mysql','host')
        self._mysql_username = config.get('mysql','username')
        self._mysql_password = config.get('mysql','password')
        self._mysql_db = config.get('mysql','db')
        self._mysql_port = config.get('mysql','port')

        self._influx_db_host = config.get('influx','host')
        self._influx_db_port = config.get('influx','port')
        self._influx_db_username = config.get('influx','username')
        self._influx_db_password = config.get('influx','password')
        self._influx_db = config.get('influx','db')

        self._complete = False
        self._check_field = config.get('mysql','check_field')

        self.initialise_database()

    def initialise_database(self):
        self._db_client = MySQLdb.connect(host=self._mysql_host,
                                          user=self._mysql_username,
                                          passwd=self._mysql_password,
                                          db=self._mysql_db,
                                          port=int(self._mysql_port),
                                          cursorclass=MySQLdb.cursors.DictCursor
                                            )

        self._influx_client = InfluxDBClient(
                                            self._influx_db_host,
                                            self._influx_db_port,
                                            self._influx_db_username,
                                            self._influx_db_password,
                                            self._influx_db
                                            )



    def transfer_data(self):
        self._get_data_from_mysql()

        self._update_rows()

        logger.debug('All data transfer  completed : %s '% self._complete)


    def _purge_data_in_db(self):
        """
        Once the data is configured and within influx we can pruge our database
        """
        if self._complete:
            query = "SELECT * FROM TABLE %s WHERE %s = 0 ORDER BY %s DESC"%(self._table, self._check_fields,self._time_field)


    def _get_data_from_mysql(self):
        """
        get the cursor to dump all the data from mysql
        """
        query = "SELECT * FROM `%s` WHERE `%s`=0 ORDER BY %s DESC"%(self._table,self._check_field,self._time_field)

        logger.debug('executing query %s '% query)
        cursor = self._db_client.cursor()
        cursor.execute(query)

        # pull data from mysql in X increments
        rows = cursor.fetchall()
        logger.info('querying MYSQL got %s rows'%len(rows))

        self._format_data(rows)


    def _send_data_to_influx(self,data_point):
        """
        Break up data to make sure in the format the inflxu like
        """
        logger.debug('Sending data to influx %s ...'%data_point[0])
        self._influx_client.write_points(data_point)


    def _format_data(self,data):
        self._complete = False
        #turn time into epoch timesa
        if data:
            logger.debug('Got data from mysql')
            counter=1;
            data_list =[]
            for row in data:
                for key in row.keys():
                    #format date to epoch
                    epoch_time = row[self._time_field].isoformat()
                    if not isinstance(row[key],datetime) and key != 'check_field':
                        data_point = {"measurement":key,
                                     "time" : "%sZ"%epoch_time,
                                   "fields" : {"value":row[key]}
                                    }

                        data_list.append(data_point)
                        logger.debug("data_point = %s"%data_point)
                if counter%100==0:
                    self._send_data_to_influx(data_list)
                    data_list =[]
                counter += 1
        self._send_data_to_influx(data_list)
        self._complete = True

    def _update_rows(self):
        query = 'UPDATE %s SET %s=1  WHERE %s=0;'%(self._table,self._check_field,self._check_field)
        if self._complete:
           logger.debug('Updating rows : executing query %s '% query)
           c =  self._db_client.cursor()
           c.execute(query)
           self._db_client.commit()
def main():
    #Argument parsing
    parser = argparse.ArgumentParser(description = 'Get Time series data from MYSQL and push it to influxdb' )

    parser.add_argument( '-d', '--debug', help = 'set logging level to debug', action = 'store_true')
    parser.add_argument( '-c', '--config', help = 'config file location', nargs = 1, default = 'settings.ini' )
    parser.add_argument( '-s', '--server', help = 'run as server with interval ',action = 'store_true' )

    args = parser.parse_args()


    # Init logging
    logging.basicConfig(level=(logging.DEBUG if True or args.debug else logging.INFO))

    logger.debug('Starting up with config file  %s' % (args.config))
    #get config file
    config = RawConfigParser()
    config.read(args.config)

    _sleep_time = float(config.get('server','interval'))

    logger.debug('configs  %s' % (config.sections()))
    #start
    mclient = Mysql2Influx(config)
    if not args.server:
        mclient.transfer_data()
    else:
        logger.info('Starting up server mode interval:  %s' % _sleep_time)
        while True:
            try:
                mclient.transfer_data()
            except Exception,e:
                logger.exception("Error occured will try again")
            time.sleep(_sleep_time)
            mclient.initialise_database()

if __name__ == '__main__':
    #Check our config file
    main()
