from __future__ import print_function
import httplib2
import os
import requests
import time
from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
import datetime

try:
    import argparse
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'ISS Station Passes'

# Get credentials to access Google Calendar
def get_credentials():
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir, 'ISS-station-passes.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

# Get a latitude and longitude from an address from Google maps API
def getLatLong(address):
    response = requests.get('https://maps.googleapis.com/maps/api/geocode/json?address=' + address)
    resp_json_payload = response.json()
    return resp_json_payload

# Get a dictionary containing the sunrise and sunset data based on location and date, in UTC timestamps
def getSunriseSunset(latitude,longitude,eventDate):
    requestString = 'http://api.sunrise-sunset.org/json?lat=' + str(latitude) + '&lng=' + str(longitude) + '&date=' + eventDate
    request = requests.get(requestString)
    sunData = request.json()
    format = '%Y-%m-%d %I:%M:%S %p'
    sunRise = time.mktime(datetime.datetime.strptime(eventDate + " " + sunData['results']['sunrise'], format).timetuple())
    sunSet = time.mktime(datetime.datetime.strptime(eventDate + " " + sunData['results']['sunset'], format).timetuple())
    sunData = {"Sunrise" : sunRise, "Sunset" : sunSet }
    return sunData

# Function to get ISS timing based on provided lat / long
def getISSPass(Latitude, Longitude, Passes):
    data = {"lat": Latitude, "lon": Longitude, "n":Passes }
    response = requests.get("http://api.open-notify.org/iss-pass.json", params=data)
    return(response.json())

def main():

    # Connect to Google Calendar
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    # Pull next 10 events
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    eventsResult = service.events().list(
        calendarId='primary', timeMin=now, maxResults=20, singleEvents=True,
        orderBy='startTime').execute()
    events = eventsResult.get('items', [])

    if not events:
        print("No upcoming events found.")
    else:
        for event in events:

            # Set some initial variables / lists
            error = ''
            visibleISSPasses = []
            nonEventISSPasses = []
            sunnyISSPasses = []

            # Get the start and end times and current time
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            currentTime = int(time.time())

            # Strip off the timezone adjustment from start and end times
            eventUTCAdjust = start[-6:]
            start = start[:-6]
            end = end[:-6]

            # Get local start and end times in timestamp format
            startTimestamp = time.mktime(datetime.datetime.strptime(start, "%Y-%m-%dT%H:%M:%S").timetuple())
            endTimestamp = time.mktime(datetime.datetime.strptime(end, "%Y-%m-%dT%H:%M:%S").timetuple())

            # Get UTC versions of current, start, and end timestamps
            timeOffset = (int(eventUTCAdjust[1:3]) * 60 * 60) + (int(eventUTCAdjust[4:6]) * 60)
            if eventUTCAdjust[0] == '-':
                startTimeUTC = startTimestamp + timeOffset
                endTimeUTC = endTimestamp + timeOffset
                currentTimeUTC = currentTime + timeOffset
            else:
                startTimeUTC = startTimestamp - timeOffset
                endTimeUTC = endTimestamp - timeOffset
                currentTimeUTC = currentTime - timeOffset

            # Print event information
            print("-------------")
            print("Event Summary: ", event['summary'])
            print("Event Start UTC: ", datetime.datetime.fromtimestamp(int(startTimeUTC)).strftime('%Y-%m-%d %H:%M:%S'))
            print("Event End UTC: ", datetime.datetime.fromtimestamp(int(endTimeUTC)).strftime('%Y-%m-%d %H:%M:%S'))

            # Get the latitude and Longitude of the event location, if available
            if 'location' in event:
                coordinates = getLatLong(event['location'])
                if coordinates['status'] == 'OK':

                    # Got coordinates.  Get sunrise / sunset data
                    sunData = getSunriseSunset(coordinates['results'][0]['geometry']['location']['lat'], coordinates['results'][0]['geometry']['location']['lng'], start[0:10])
                    print("Sunrise UTC: ", datetime.datetime.fromtimestamp(int(sunData['Sunrise'])).strftime('%Y-%m-%d %H:%M:%S'))
                    print("Sunset UTC: ", datetime.datetime.fromtimestamp(int(sunData['Sunset'])).strftime('%Y-%m-%d %H:%M:%S'))
                    print("Event Location: ", event['location'])
                    print("Event Latitude: ", coordinates['results'][0]['geometry']['location']['lat'])
                    print("Event Longitude: ", coordinates['results'][0]['geometry']['location']['lng'])
                    print("-------------")
                    print("")

                    # Check to see if this event has any darkness hours
                    if (startTimeUTC < int(sunData['Sunrise']) or startTimeUTC > int(sunData['Sunset'])) or (endTimeUTC > int(sunData['Sunset'])):

                        # Calculate how many passes of the ISS will need to be calculated to cover this event
                        orbitTimeInMinutes = 92
                        numberOfPasses = round((endTimeUTC - currentTimeUTC) / (orbitTimeInMinutes * 60), )

                        # Get the pass information from the API
                        ISSPasses = getISSPass(coordinates['results'][0]['geometry']['location']['lat'], coordinates['results'][0]['geometry']['location']['lng'], numberOfPasses)
                        if ISSPasses['message'] == 'success':
                            ISSPasses = ISSPasses['response']

                            # Go through all the passes, and only care about the ones that occur during darkness hours of the event date (if any)
                            for isspass in ISSPasses:
                                if (int(isspass['risetime']) < int(sunData['Sunrise']) or int(isspass['risetime']) > int(sunData['Sunset'])) or ((int(isspass['risetime']) + int(isspass['duration'])) > int(sunData['Sunset'])):

                                    # Now print it if it occurs during the actual event hours
                                    if (int(isspass['risetime']) < startTimeUTC and (int(isspass['risetime']) + int(isspass['duration'])) > startTimeUTC) or (int(isspass['risetime']) > startTimeUTC and int(isspass['risetime']) < endTimeUTC):
                                        visibleISSPasses.append(datetime.datetime.fromtimestamp(int(isspass['risetime'])).strftime('%Y-%m-%d %H:%M:%S'))
                                    else:
                                        nonEventISSPasses.append(datetime.datetime.fromtimestamp(int(isspass['risetime'])).strftime('%Y-%m-%d %H:%M:%S'))

                                else:
                                    sunnyISSPasses.append(datetime.datetime.fromtimestamp(int(isspass['risetime'])).strftime('%Y-%m-%d %H:%M:%S'))

                        else:
                            error = '   *Unable to get ISS passes from API.'

                    else:
                        error = '   *Event does not contain any darkness hours.'
            else:
                error = '   *No location available from this event.'

            if error != '':
                print('')
                print('Error: ', error)
            else:
                print(' Visible ISS passes during your event: (', len(visibleISSPasses), ')')
                for visiblepass in visibleISSPasses:
                    print('     ', visiblepass)
                print("")
                print(' Non-visible ISS passes during your event, due to sunshine: (', len(sunnyISSPasses), ')')
                for sunnyISSPass in sunnyISSPasses:
                    print('     ', sunnyISSPass)
                print("")
                print(' Passes which occur outside the event window: (', len(nonEventISSPasses), ')')
                for nonEventISSPass in nonEventISSPasses:
                    print('     ', nonEventISSPass)
                print("")

            print("")

if __name__ == '__main__':
    main()