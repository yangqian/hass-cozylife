DOMAIN = "cozylife"

# http://doc.doit/project-5/doc-8/
SWITCH_TYPE_CODE = '00'
LIGHT_TYPE_CODE = '01'
SUPPORT_DEVICE_CATEGORY = [SWITCH_TYPE_CODE, LIGHT_TYPE_CODE]

CONF_DEVICE_TYPE_CODE = "device_type_code"
CONF_SUBNET = "subnet"
CONF_DEVICES = "devices"

PLATFORMS = ["light", "switch"]

PLATFORMS_BY_TYPE = {
    LIGHT_TYPE_CODE: "light",
    SWITCH_TYPE_CODE: "switch",
}

# http://doc.doit/project-5/doc-8/
SWITCH = '1'
WORK_MODE = '2'
TEMP = '3'
BRIGHT = '4'
HUE = '5'
SAT = '6'

LIGHT_DPID = [SWITCH, WORK_MODE, TEMP, BRIGHT, HUE, SAT]
SWITCH_DPID = [SWITCH, ]

# Default color temperature bounds (Kelvin)
DEFAULT_MIN_KELVIN = 2700
DEFAULT_MAX_KELVIN = 6500
