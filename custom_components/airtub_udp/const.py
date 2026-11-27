DOMAIN = "airtub_udp"
EVENT_NEW_DATA = "airtub_new_data_received"
PLATFORMS = ("sensor", "climate")
UDP_GROUP = "224.0.1.3"
UDP_PORT = 4211

# 收到第一帧数据前使用的完整默认数据。
# 实体按这份键集创建，避免设备/固件某些工况下不返回个别字段时对应实体消失。
DEFAULT_DATA = {
    "sch": 0,
    "loc": 0,
    "tmd": 0,
    "tol": 4,
    "mod": 0,
    "flt": 0,
    "tcm": 0,
    "tct": 0,
    "ccm": 0,
    "cct": 0,
    "tdm": 0,
    "tdt": 0,
    "cdm": 0,
    "cdt": 0,
    "atm": 0,
    "trt": 0,
    "crt": 0,
    "pwr": 0,
    "odt": 0,
    "coe": 0,
    "fst": 0,
    "ovr": 0,
    "gas": 0.000001,
}
