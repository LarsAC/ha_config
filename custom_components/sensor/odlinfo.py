import logging
import voluptuous as vol
from datetime import timedelta
import requests
from requests.auth import HTTPBasicAuth

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_LONGITUDE, CONF_LATITUDE

DOMAIN = 'odlinfo'

CONF_DISTANCE = 'distance'
CONF_STATIONS = 'stations'

USIEVERT = 'uSv/h'

ODL_BASE_URL   = 'https://odlinfo.bfs.de/daten/json/'
LOCATION_KEY   = 'ort'
STATUS_KEY     = 'status'
METADATA_KEY   = 'stamm'
STATUS_VALUES  = { 0 : 'Defunct', 1 : 'OK', 128 : 'Test', 2048 : 'Maintenenance' }
ATTR_ID        = 'odlid'
ATTR_STATUS    = 'status'
ATTR_TIMESTAMP = 'timestamp'
ATTR_FRIENDLY_NAME = 'friendly_name'

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=300)

PLATFORM_SCHMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_STATIONS): cv.ensure_list,
    vol.Optional(CONF_DISTANCE, default=0): cv.positive_int,
    })

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""
    my_config = config.get(DOMAIN, {})
    longitude = config.get(CONF_LONGITUDE, round(hass.config.longitude, 5))
    latitude = config.get(CONF_LATITUDE, round(hass.config.latitude, 5))
        
    user = config.get(CONF_USERNAME)
    pwd  = config.get(CONF_PASSWORD)
    stations = config.get(CONF_STATIONS)
    distance = config.get(CONF_DISTANCE)

    data = OdlData(user, pwd)
    
    metadata = load_metadata (user, pwd)

    # Configure sensors for fixed stations
    devices = []
    if len(stations) > 0:
        devices += [ create_sensor(s, metadata, data) for s in stations ]

    # Think about a different approach:
    # - make a MaxSensor with the largest measurement value
    # - attributes of max sensor for distance and station name
    # - enables automation triggered when max goes over a threshold
    # - OR make this a binary sensor with distance, threshold ?
    #   - Sensor would be turned on as long as any sensor has value
    #     larger than threshold within specified distance
    
    # Configure sensors via distance (if distance given)
    # if distance > 0:
    #    devices.append( create_sensors_within_radius( metadata, data, distance, longitude, latitude ) )

    add_devices( devices )

def load_metadata(user, password):

    url = ODL_BASE_URL + 'stamm.json'
    session = requests.Session()        

    try:
        response = session.get(url, auth = HTTPBasicAuth(user, password) )
    except Exception as e:
        _LOGGER.error(
            "Exception when sending GET request for load_metadata: %s" % str(e))
        return

    json_obj = response.json()
    return json_obj
    
def create_sensor( odlinfo_id, metadata, data ):
    """ Create a sensor for a given station id """

    sensor = None
    if metadata[odlinfo_id]:
        sensor = OdlSensor(odlinfo_id, data)
            
    return sensor

def create_sensors_within_radius(metadata, data, distance, lon_home, lat_home):
    """ Create sensors for a maximum distance away from a given centerpoint """
    stations = []
    
    for s in metadata.keys():
        station = metadata[s]

        lon = station['lon']
        lat = station['lat']
        
        distance = calc_distance(lon_home, lat_home, lon, lat)
        ort = station['ort']

        sensor = create_sensor(s, metadata, data)
        stations.append( sensor )

class OdlSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, station_id, data):
        """Initialize the sensor."""
        self._data = data

        self._state = None
        self._status = 1
        self._odl_id = station_id
        self._name = 'odlinfo.' + str(station_id)
        self._location = 'unknown'
        self._timestamp = 'unknown'

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'odlinfo_' + str(self._odl_id)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return USIEVERT

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_ID: self._odl_id,
            ATTR_TIMESTAMP: self._timestamp,
            ATTR_STATUS: self._status,
            ATTR_FRIENDLY_NAME: self._location,
        }
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        d = self._data.load(self._odl_id)

        self._location = d[METADATA_KEY][LOCATION_KEY]

        s = d[METADATA_KEY][STATUS_KEY]
        self._status   = STATUS_VALUES[s]

        self._state = d['mw1h']['mw'][-1]
        self._timestamp = d['mw1h']['t'][-1]
        
class OdlData(object):

    def __init__(self, username, password):
        self._username = username
        self._password = password

    def load(self, station_id):
        url = ODL_BASE_URL + str(station_id) + '.json'
        session = requests.Session()

        try:
            response = session.get(url, auth = HTTPBasicAuth(self._username, self._password) )
        except Exception as e:
            _LOGGER.error("Exception when sending GET request for load_metadata: %s" % str(e))
            return

        json_obj = response.json()
        return json_obj
