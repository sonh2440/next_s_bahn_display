# -*- coding: utf-8 -*-
"""
Created on Tue May 24 15:42:14 2016
Author: Edouard Fouché
"""
from __future__ import print_function
from my_database import MyDatabase
from RPLCD.i2c import CharLCD
import schiene
import datetime
import time
import os
import sys, getopt
import threading

def sanitize(req):
    """Enhance the information content"""
    # get current time
    now = datetime.datetime.now()
    time_now = datetime.datetime.strptime(now.strftime("%H:%M"),"%H:%M")

    for i,s in enumerate(req):        
        if s.get("ontime", False):      # If ontime is not contained in the list, False is returned
            req[i]['status'] = "+0"
        elif "delay" in s:
            req[i]['status'] = "+%s"%s['delay']['delay_departure']
        elif s.get("canceled", False):
            req[i]['status'] = "X"
        else:
            req[i]['status'] = ""

        time_to_wait = round(abs((datetime.datetime.strptime(s['departure'],"%H:%M") - time_now)).seconds/60)
        if time_to_wait < 1000:
            req[i]['time_to_wait'] = str(time_to_wait)
        else:
            req[i]['time_to_wait'] = str(1440-time_to_wait)
    return req

class DeutscheBahnTimeDisplay():
    def __init__(self, database, refresh=30):
        self.schiene = schiene.Schiene() # initialize crawler
        self.trips = [] # Contains the trips we are interested in
        self.display_terminal = [] # Contains the strings to display
        self.display_lcd = "" # contains the string to send to the lcd display
        self.lcd = CharLCD('PCF8574',0x27)
        self.refresh = refresh
        self.database = database
        
    def add_trip(self, start, goal, prefix=None, only_direct=False):
        """
        Add a streak to be displayed on the list.
        Each streak should be defined by a start, a goal and optional a prefix
        
        Arguments
        ---------
            start: str
                Start station (as on the DB website)
            goal: str
                Goal station (as on the DB website)
            prefix: str, optional
                The prefix of the streak you want to show (to be printed)
                We recommend a string of 7 characters of the shape "=XXXX=>",
                where X can be either additional "=" or an abbreviation for
                your trip/destination.
                If no prefix is given, it will be set to "=XX===>" where XX are
                the first 2 capitalized letters of the destination of the trip. 
            only_direct: bool, default: False
                If True, return only direct connections. 
        """
        if prefix is None: 
            prefix = "=%s===>"%(goal[0:2].upper())

        self.trips.append({"start":start, "goal":goal, "prefix":prefix, 
                           "only_direct":only_direct})
                
    def run(self):   
        """Run the app and display the result, forever."""  
        fetcher = threading.Thread(target=self.get_data)
        fetcher.start()
        fetcher.join() # Need to wait for the first time. 

        j = 0           
        while(True):

            # Plot results to external display here
            print("LCD Output total:", self.display_lcd)
            self.lcd.clear()
            if len(self.display_lcd) > 0 :
                self.lcd.cursor_pose = (0,0)
                self.lcd.write_string(self.display_lcd[0])
                self.lcd.cursor_pose = (1,0)
                self.lcd.write_string("    " + self.display_lcd[1])
            else:
                self.lcd.write_string("DB API Unreachable")

            #print the content of each trip in self.display_terminal on the terminal              
            for i in range(30):
                # Clear the terminal before refreshing text
                # os.system('cls' if os.name == 'nt' else 'clear')

                if len(self.display_terminal) > 0 and i % 5 == 0: # change displayed trip every 5 units 
                    j = (j+1)%len(self.display_terminal)
                
                # Print results in terminal
                #print("%s/%s==========================="%(j+1,len(self.display_terminal))) # just esthetic 
                #print(self.display_terminal[j])    
                #print('.'*(i+1))#,end="\r")

                time.sleep(self.refresh/30)

            # Start routine to refresh data in a parallel thread 
            fetcher = threading.Thread(target=self.get_data)
            fetcher.start()

    def get_data(self):
        newdisplayterminal = []
        newdisplaylcd = []
        for trip in self.trips:
            append_to_terminal, append_to_lcd = self.format_information(trip)
            newdisplayterminal.append(append_to_terminal)
            newdisplaylcd.append(append_to_lcd)

        self.display_terminal = newdisplayterminal # Overwrite information from last iteration
        self.display_lcd = newdisplaylcd
            
    def format_information(self, trip, delta =3):
        """
        Parse and return the current string to be printed corresponding to next 
        travel possibiblities between start and goal.
        Delta is used to restrict the trips to be at least in a number of minutes
        """

        # get current time
        now = datetime.datetime.now() + datetime.timedelta(minutes = delta)

        start = trip['start']
        goal = trip['goal']
        prefix = trip['prefix']

        try:
            # Get the next trips from now
            conn1 = self.schiene.connections(start, goal, now,
                                           only_direct=trip['only_direct'])
            #print("Dbg Conn1:", conn1)
            # Get the next trips after last trip return. This increase the list of results :) 
            last_departure = conn1[-1]['departure']
            next_time = now.replace(hour=int(last_departure.split(":")[0]), minute=int(last_departure.split(":")[1]))
            if(int(last_departure.split(":")[0]) < now.hour): # That means that it is after midnight then 
                next_time = next_time + datetime.timedelta(days = 1)
            conn2 = self.schiene.connections(start, goal, next_time + datetime.timedelta(minutes = 1),
                                           only_direct=trip['only_direct'])
            #print("Dbg Conn2:", conn2)
            conn = conn1 + conn2

            # Todo sorting out duplicates in conn would be nice. 

        except Exception as e:
            print("Could not fetch Data from Schiene.")
            raise e
        else: 
            conn = sanitize(conn) # Parse the raw data gained from the crawler
            
            time_to_wait_list = [str(int(float(x['time_to_wait']))) for x in conn]
            product_list = [','.join(x['products']) for x in conn]
            departure_list = [x['departure'] for x in conn]
            time_list = [x['time'] for x in conn]
            status_list = [x['status'] for x in conn]

            max_product_length = max([len(x) for x in product_list])
            if max_product_length < 1:
                print("Could fetch data from Schiene, but not parse them properly.")
                return "",""

            # Output for terminal
            output_terminal = "%s %s"%(prefix, ",".join(time_to_wait_list))
            for i, el in enumerate(product_list):
                output_terminal += "\n"
                prod = product_list[i]
                if len(prod) < max_product_length: # esthetic tuning
                    prod = prod + " "*(max_product_length - len(prod))
                output_terminal += "%s | %s | %s %s"%(prod, departure_list[i], 
                                            time_list[i], status_list[i])
                
            # Output for lcd display (Only first departure, idx 0)
            output_lcd = ""
            output_lcd += "%s| %s | %s"%(prod, departure_list[0], status_list[0])
            # Fill spaces for the rest of the line of 16 digit lcd display
            output_lcd = output_lcd.ljust(16)

            print("Debug LCD: ", output_lcd)
                
            #store received trip info in the database
            if len(output_terminal) > 0:
                print("Debug: Trip from ", trip['start'], " to ", trip['goal'])
                print("Debug: Year ", now.year, " month ", now.month, " day ", now.day, " hour ", now.hour," min ", now.minute, " product ", product_list[0], " etd ", departure_list[0], " delay ", status_list[0])
                if product_list[0] == 'BUS':
                    self.database.store_data_harras(now.year, now.month, now.day, now.hour, now.minute, product_list[0], trip['start'], trip['goal'], departure_list[0], status_list[0])
                elif product_list[0] == 'S':
                    self.database.store_data_hbf(now.year, now.month, now.day, now.hour, now.minute, product_list[0], trip['start'], trip['goal'], departure_list[0], status_list[0])
                else:
                    print("ERROR: Coult not identify product")
            else:
                print("No data to store in database.")
        
            return output_terminal, output_lcd
        
def main(argv):
    """
    Each trip are characterized by 4 Arguments
    - The first one: Start
    - The second one: Destination
    - The third one: prefix (7 letters zith an arrow is better, e.g; =WORK=>)
    - The fourth one: If we should only consider direct connections (True) or not (False)
    """
    #python dbtime.py "Stuttgart HbF" "Karlsruhe HbF" "==KA==>" True "Schwabstraße, Stuttgart" "Leinfelden Frank, Leinfelden-Echterdingen" "=ROTO=>" False
    refresh = 45 # Number of seconds that we should wait before refreshing
    database = MyDatabase()
    app = DeutscheBahnTimeDisplay(database, refresh)
    
    # In the following lines, declare the trips you are interested in 
    if len(argv) == 0:
        app.add_trip(start='München-Mittersendling', goal='München Hbf', prefix= "=HBF=>", only_direct=True)
        app.add_trip(start='Steinerstraße, München', goal='Am Harras, München', prefix= "=HARR=>", only_direct=True)
    else:
        if len(argv)%4 != 0:
            raise ValueError("Arguments need to be composed of 4 terms, see documentation.")

        for x in range(int(len(argv)/4)):
            app.add_trip(start=argv[4*x], goal=argv[4*x+1], prefix= argv[4*x+2], only_direct=argv[4*x+3] == "True")
    

    while(True):
        try:
            app.run()
        except Exception as e:
            for i in range(60):
                # Plot results to display here
                lcd = CharLCD('PCF8574',0x27)
                lcd.clear()
                lcd.write_string("Error: Restart i    n 60s")
                
                os.system('cls' if os.name == 'nt' else 'clear')
                print("Error: %s"%str(e))
                print("Restarting in 60 seconds") 
                print('.'*(i+1))#,end="\r")
                time.sleep(60/25)


if __name__ == '__main__': 
    main(sys.argv[1:])
