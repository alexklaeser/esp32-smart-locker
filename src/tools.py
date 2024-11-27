import ujson
import contextlib
from machine import Pin, SoftSPI
from mfrc522 import MFRC522
import random
import asyncio


def load_credentials():
    with open("credentials.txt") as f:
        username = f.readline().strip()
        password = f.readline().strip()
    return username, password


USERNAME, PASSWORD = load_credentials()


def load_authorized_uids():
    try:
        with open("/authorized_uids.json") as f:
            return ujson.load(f)
    except:
        return []


_tags = load_authorized_uids()


def save_authorized_uids(tags):
    global _tags
    with open("/authorized_uids.json", "w") as f:
        ujson.dump(tags, f)
    _tags = tags


def add_uid(uid, username, timestamp):
    global _tags
    if not is_uid_registered(uid):
        _tags.append(dict(uid=uid, username=username, timestamp=timestamp))
        save_authorized_uids(_tags)


def remove_uid(uid):
    global _tags
    tags = [i for i in _tags if i['uid'] != uid]
    if len(tags) != len(_tags):
        save_authorized_uids(tags)


def is_uid_registered(uid):
    global _tags
    uids = set([i['uid'] for i in _tags])
    return uid in uids


sck = Pin(14, Pin.OUT)
mosi = Pin(15, Pin.OUT)
miso = Pin(35)
spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=sck, mosi=mosi, miso=miso)
sda = Pin(2, Pin.OUT)
reader = MFRC522(spi, sda)

_open_cash_allowed = True


@contextlib.contextmanager
def disable_opening_cash_register():
    global _open_cash_allowed
    x = _open_cash_allowed
    _open_cash_allowed = False
    try:
        yield x
    finally:
        _open_cash_allowed = x


async def open_cash_register():
    if not _open_cash_allowed:
        return
    relay = Pin(13, Pin.OUT)
    relay.value(0)
    await asyncio.sleep_ms(300)
    relay.value(1)


def start_rfid_reading():
    asyncio.create_task(_rfid_reading())


_last_uid = None
_n_status_err = 0


async def _rfid_reading():
    global _last_uid, _n_status_err
    while True:
        (status, tag_type) = reader.request(reader.CARD_REQIDL)
        if status == reader.OK:
            (status, raw_uid) = reader.anticoll()
            if status == reader.OK:
                uid = ''.join('{:02X}'.format(x) for x in raw_uid)
                print('_rfid_reading: Card Detected: %s' % uid)
                print('')
                if _last_uid is None and is_uid_registered(uid):
                    await open_cash_register()
                _last_uid = uid
                _n_status_err = 0
        else:
            _n_status_err += 1
            if _n_status_err >= 2:
                _last_uid = None

        await asyncio.sleep_ms(250)


async def read_uid():
    global _last_uid

    # try a few times to read the UID
    for i in range(20):
        if _last_uid is not None:
            return _last_uid
        # allow for some randomness here, to avoid race conditions with RFID reading thread
        await asyncio.sleep_ms(random.randint(200, 300))

    # no card read until now
    return None
