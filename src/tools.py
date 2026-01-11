import asyncio

import ujson
from machine import Pin, SoftSPI
from mfrc522 import MFRC522


def values2hexstr(uid):
    return '0x' + ''.join(f'{i:02X}' for i in uid) if uid else 'unknown'


def hexstr2values(hex_string, default=None):
    if hex_string is None or not hex_string.startswith('0x'):
        return default
    hex_string = hex_string[2:]  # Remove '0x' prefix
    return [int(hex_string[i : i + 2], 16) for i in range(0, len(hex_string), 2)]


class SimpleINIParser:
    """
    A simple INI-style configuration file parser.
    Reads key-value pairs from a file with format: key=value.
    Ignores empty lines and comments starting with '#'.
    """

    def __init__(self, filename):
        """Initialize the parser with a given filename."""
        self.filename = filename
        self.data = {}
        self._load()

    def _load(self):
        """Load key-value pairs from the file into a dictionary."""
        try:
            with open(self.filename) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue  # Skip empty lines and comments
                    if '=' in line:
                        key, value = map(str.strip, line.split('=', 1))
                        self.data[key] = value
        except OSError:
            pass  # Handle missing file gracefully

    def get(self, key, default=None):
        """Retrieve the value associated with a key, or return a default value."""
        return self.data.get(key, default)

    def set(self, key, value):
        """Set a key-value pair and save it to the file."""
        self.data[key] = value
        self._save()

    def _save(self):
        """Save the current key-value pairs back to the file."""
        with open(self.filename, 'w') as f:
            f.writelines(f'{key}={value}\n' for key, value in self.data.items())

    def set_hex(self, key, values):
        """Store a list of int values as a hex string prefixed with '0x'."""
        hex_string = values2hexstr(values)
        self.set(key, hex_string)

    def get_hex(self, key, default=None):
        """Retrieve a hex string prefixed with '0x' and convert it back to a list of integers."""
        hex_string = self.get(key, default)
        return hexstr2values(hex_string, default)


class AuthorizedRFIDStore:
    """
    Singleton store for authorized RFID tags.

    Handles:
    - Persistent storage in JSON file
    - In-memory caching
    - Basic CRUD operations on RFID UIDs
    """

    _instance = None
    _file = '/authorized_uids.json'

    def __new__(cls):
        """Ensure exactly one instance exists (Singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tags = cls._instance._load()
        return cls._instance

    # ---------- internal ----------

    def _load(self):
        """
        Load authorized RFID tags from JSON file.

        Returns:
            List of RFID tag entries.

        """
        try:
            with open(self._file) as f:
                return ujson.load(f)
        except:
            return []

    def _save(self):
        """Persist the current RFID tag list to the JSON file."""
        with open(self._file, 'w') as f:
            ujson.dump(self._tags, f)

    # ---------- public API ----------

    def get_all(self):
        """
        Return all authorized RFID tags.

        Returns:
            List of RFID tag records. Each record is a list of the format:
            [<uid>, <username>, <collmex_id>, <timestamp>]

        """
        return self._tags

    def is_uid_registered(self, uid):
        """
        Check whether a UID is already registered.

        Parameters
        ----------
            uid : str
                RFID UID to check.

        Returns
        -------
            True if UID exists, False otherwise.

        """
        return any(t[0] == uid for t in self._tags)

    def add(self, uid, username, collmex_id, timestamp):
        """
        Add a new authorized RFID UID. Any UID entry is unique.

        Parameters
        ----------
            uid : str
                Unique RFID UID.
            username : str
                Human-readable user name for the web frontend.
            collmex_id : str
                ID for access to the Collmex service.
            timestamp : str
                Registration timestamp as ISO string.

        """
        if not self.is_uid_registered(uid):
            self._tags.append([uid, username, collmex_id, timestamp])
            self._save()

    def remove(self, uid):
        """
        Remove an RFID UID from the authorized list.

        Parameters
        ----------
        uid : str
            RFID UID to remove.

        """
        new_tags = [t for t in self._tags if t[0] != uid]
        if len(new_tags) != len(self._tags):
            self._tags = new_tags
            self._save()


config = SimpleINIParser('config.ini')

# RFID keys
DEFAULT_KEY = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
CUSTOM_KEY = config.get_hex('key')

sck = Pin(14, Pin.OUT)
mosi = Pin(15, Pin.OUT)
miso = Pin(35)
spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=sck, mosi=mosi, miso=miso)
sda = Pin(2, Pin.OUT)
reader = MFRC522(spi, sda)
reader_lock = asyncio.Lock()

# Data sector to use
SECTOR_META = 1
SECTOR_USERNAME = 2
SECTOR_COLLMEX_ID = 3
SECTOR_PASSWORD = 4

# Access flags
FLAG_CASH_REGISTER = 0b0001


class RFIDException(Exception):
    """Base exception class for all RFID-related errors."""


class NoCardDetectedException(RFIDException):
    """Raised when no RFID card is detected within the timeout."""


class AccessDeniedException(RFIDException):
    """Raised when an unauthorized card tries to access the system."""


class AuthenticationFailureException(RFIDException):
    """Raised when authentication with an RFID key fails."""


class ReadWriteFailureException(RFIDException):
    """Raised when reading from or writing to the RFID card fails."""


class UnexpectedMetaDataException(RFIDException):
    """Raised when the expected meta data is not as expected."""


def uid2str(uid):
    return values2hexstr(uid)


def _normalize_key(key):
    if key is None:
        return None
    if isinstance(key, (bytes, bytearray)):
        key = list(key)
    if not isinstance(key, list) or len(key) != 6:
        raise ValueError('RFID key must be 6 bytes (list[int]/bytes/bytearray).')
    return key


def _normalize_uid(uid):
    if uid is None:
        return
    if isinstance(uid, (bytes, bytearray)):
        uid = list(uid)
    if not isinstance(uid, list) or len(uid) not in {4, 7, 10}:
        # ISO14443A UIDs are typically 4, 7, or 10 bytes
        raise ValueError('UID must be 4/7/10 bytes (list[int]/bytes/bytearray).')
    return


def card_session(func):
    """
    Decorator function for reading and accessing an RFID tag.
    - Detect + (optional) anticoll + select_tag
    - Optional: uid/key can be passed via kwargs
    - Iterate over keys (if key not forced)
    - Re-select and stop_crypto1 between attempts
    - Pass (uid, key, ...) into wrapped function.
    """

    async def wrapper(*args, **kwargs):
        # Optional overrides (and remove them from kwargs so func() doesn't get duplicates)
        forced_uid = kwargs.pop('uid', None) or kwargs.pop('raw_uid', None)
        forced_key = kwargs.pop('key', None)
        n_trials = kwargs.pop('n_trials', 3)
        time_between_trials_ms = kwargs.pop('time_between_trials_ms', 250)
        unlocked = kwargs.pop('unlocked', False)

        async def _logic_wrapper():
            # determine key candidates
            key_candidates = [_normalize_key(forced_key)] if forced_key is not None else [_normalize_key(k) for k in (DEFAULT_KEY, CUSTOM_KEY)]
            uid_str = '<unknown>'

            for ikey in key_candidates:
                try:
                    # try the request operation a few times, it might fail once in a while
                    for _itrial in range(n_trials):
                        status, tag_type = reader.request(reader.CARD_REQIDL)
                        if status == reader.OK:
                            break
                        await asyncio.sleep_ms(time_between_trials_ms)
                    else:
                        raise NoCardDetectedException('No RFID card detected.')

                    print(f'Card detected! Tag Type: 0x{tag_type:02X}')
                    if tag_type == 0x08:
                        print('MIFARE Classic 1K detected.')
                    elif tag_type == 0x10:
                        print('MIFARE Classic 4K detected.')
                    elif tag_type == 0x04:
                        print('MIFARE Ultralight detected.')
                    elif tag_type == 0x44:
                        print('MIFARE DESFire detected.')
                    elif tag_type == 0x20:
                        print('MIFARE Plus detected.')
                    elif tag_type == 0x40:
                        print('MIFARE Mini detected.')
                    else:
                        print('Unknown or unsupported card type.')

                    # identify accessible RFID card
                    status, uid = reader.anticoll()
                    if status != reader.OK or not uid:
                        raise ReadWriteFailureException('Failed to access card UID via anticoll().')

                    if forced_uid is not None and uid != forced_uid:
                        msg = f'Failed to access the given UID {uid2str(forced_uid)}.'
                        raise NoCardDetectedException(msg)

                    uid_str = uid2str(uid)

                    # connect to the identified RFID card
                    if reader.select_tag(uid) != reader.OK:
                        msg = f'Failed to select RFID tag with UID: {uid_str}'
                        raise AccessDeniedException(msg)

                    # Call the wrapped function with (uid, key)
                    res = func(*args, uid=uid, key=ikey, **kwargs)
                    if hasattr(res, '__await__'):
                        res = await res
                    return res

                except (AuthenticationFailureException, ReadWriteFailureException):
                    print(f'Access to card {uid_str} with key {ikey} failed... trying next key')

                finally:
                    # keep crypto state clean after each attempt (success or fail)
                    reader.stop_crypto1()

            msg = f'Cannot access RFID card {uid_str} with provided/known keys.'
            raise AuthenticationFailureException(msg)

        # ignore locking
        if unlocked:
            return await _logic_wrapper()

        # respect locking
        async with reader_lock:
            return await _logic_wrapper()

    return wrapper


def sector_session(*, is_trailer_block=False):
    """
    Decorator for wrapping any operation that needs an authenticated sector.

    Parameters (decorator-level):
      is_trailer_block (bool):
        - False (default): authenticate on sector start block
        - True: authenticate on sector trailer block

    Requires kwargs at call time:
      uid, key, sector
    """

    def deco(func):
        def wrapper(*args, **kwargs):
            if 'uid' not in kwargs:
                raise ValueError("Missing required keyword argument: 'uid'")
            if 'key' not in kwargs:
                raise ValueError("Missing required keyword argument: 'key'")
            if 'sector' not in kwargs:
                raise ValueError("Missing required keyword argument: 'sector'")

            uid = kwargs['uid']
            key = _normalize_key(kwargs['key'])
            kwargs['key'] = key
            sector = kwargs['sector']

            # choose authentication block and authenticate access
            auth_block = get_sector_trailer(sector) if is_trailer_block else get_start_block(sector)

            if reader.auth(reader.AUTH, auth_block, key, uid) != reader.OK:
                msg = f'Authentication failure (sector={sector}, block={auth_block}).'
                raise AuthenticationFailureException(msg)

            return func(*args, **kwargs)

        return wrapper

    return deco


def get_start_block(sector):
    """
    Calculate the starting block for the sector
    The first 32 sectors (0–31) each have 4 blocks: 32 × 4 = 128 blocks.
    Starting from sector 32, each sector has 16 blocks.
    """
    if sector < 32:
        return sector * 4
    return 128 + (sector - 32) * 16


def get_sector_trailer(sector):
    """
    Returns for the given sector the trailing block, i.e. the 4th block for sectors 0-31
    and the 16th block for sectors >= 32.
    """
    if sector < 32:  # Sectors 0–31 (4-block sectors)
        return (sector * 4) + 3
    # Sectors 32–39 (16-block sectors)
    return (sector * 16) + 15


@sector_session()
def _write_sector(data, sector=None, uid=None, key=None):
    """Write data string (UTF-8 encoded) into the sector blocks (over all data blocks of the sector)."""
    start_block = get_start_block(sector)

    # Convert string to bytes if necessary
    if isinstance(data, str):
        data = data.encode('utf-8')  # Convert string to bytes

    # Ensure data is exactly 3 blocks with 16 bytes each (48 bytes)
    if len(data) > 48:
        raise ReadWriteFailureException('Data exceeds the maximum size of 3 blocks (48 bytes).')

    # Pad the data to fill all 15 blocks
    if len(data) < 48:
        data += b'\x00' * (48 - len(data))

    # Write the data block by block
    for i in range(0, 48, 16):
        block_number = start_block + (i // 16)
        block_data = data[i : i + 16]
        if reader.write(block_number, block_data) != reader.OK:
            msg = f'Failed to write Block {block_number}.'
            raise ReadWriteFailureException(msg)


@sector_session()
def _read_sector(sector=None, uid=None, key=None):
    """Read data from all blocks of the given sector and return the data as string (UTF-8 encoded)."""
    start_block = get_start_block(sector)

    # Buffer to hold the read data
    data = b''

    # Read the data block by block
    for i in range(3):  # 3 blocks to read
        block_number = start_block + i
        # Read the block
        block_data = reader.read(block_number)
        if block_data:
            data += bytes(block_data)  # Append the read data to the buffer
        else:
            msg = f'Failed to read Block {block_number}.'
            raise ReadWriteFailureException(msg)

    # Remove null bytes and convert to string
    return data.rstrip(b'\x00').decode('utf-8')


@card_session
def read_uid(uid=None, key=None):
    """
    Reads and returns the UID of the RFID card.

    Returns:
        list[int]: 5-byte card UID

    """
    return uid


@card_session
def test_auth(uid=None, key=None):
    """
    Authenticate all required custom card sectors.

    Args:
        uid (list[int] | None): UID of the RFID card.
        key (list[int] | None): 6-byte authentication key for the card.
            If not specified, default and custom keys are applied.

    Returns:
        bool: True if all sectors authenticate successfully, False otherwise.

    """
    for isector in (SECTOR_META, SECTOR_USERNAME, SECTOR_COLLMEX_ID, SECTOR_PASSWORD):
        istart_block = get_start_block(isector)
        if reader.auth(reader.AUTH, istart_block, key, uid) != reader.OK:
            print(f'Cannot access sector {isector} with key {key}')
            return False
    return True


@card_session
def check_valid_meta_format(uid=None, key=None):
    """
    Validates the metadata sector format and prefix.

    The metadata must follow the format '<PREFIX>_<FLAGS>' and the prefix
    must match the configured meta prefix.

    Args:
        uid (list[int] | None): UID of the RFID card.
        key (list[int] | None): 6-byte authentication key for the card.
            If not specified, default and custom keys are applied.

    Returns:
        bool: True if the metadata format is valid and the prefix matches, False otherwise.

    """
    meta_data = _read_sector(sector=SECTOR_META, uid=uid, key=key)
    if '_' not in meta_data:
        return False

    meta_prefix, flags_str = meta_data.split('_', 1)
    if meta_prefix != config.get('meta_prefix'):
        return False

    return flags_str.isdigit()


@card_session
def write_data(username, collmex_id, password, uid=None, key=None, flags=None, meta_data=None):
    """
    Writes user-related data and metadata to the RFID card into separate sectors.

    Args:
        username (str): Username to store on the card.
        collmex_id (str): Collmex identifier to store.
        password (str): Password to store.
        uid (list[int] | None): Explicit UID of the RFID card.
        key (list[int] | None): 6-byte authentication key for the card.
            If not specified, default and custom keys are applied.
        flags (int | None): Optional metadata flags; defaults to FLAG_CASH_REGISTER.
        meta_data (str | None): Optional string for the meta data field.

    Returns:
        bool: True if all sectors were written successfully.

    """
    if flags is None:
        flags = 0

    if meta_data is None:
        meta_data = '{}_{}'.format(config.get('meta_prefix'), flags)

    _write_sector(meta_data, uid=uid, key=key, sector=SECTOR_META)
    _write_sector(username, uid=uid, key=key, sector=SECTOR_USERNAME)
    _write_sector(collmex_id, uid=uid, key=key, sector=SECTOR_COLLMEX_ID)
    _write_sector(password, uid=uid, key=key, sector=SECTOR_PASSWORD)

    print('Data written successfully.')
    return True


@card_session
def read_data(uid=None, key=None):
    """
    Reads and validates structured data from the RFID card.

    Args:
        uid (list[int] | None): Explicit UID of the RFID card.
        key (list[int] | None): 6-byte authentication key for the card.
            If not specified, default and custom keys are applied.

    Returns:
        dict: Dictionary containing UID, user data, metadata flags,
              and the metadata prefix.

    Raises:
        UnexpectedMetaDataException: If the metadata format or prefix is invalid.

    """
    meta_data = _read_sector(sector=SECTOR_META, uid=uid, key=key)
    if '_' not in meta_data:
        raise UnexpectedMetaDataException('The meta data sector did not match the expected format!')

    meta_prefix, flags_str = meta_data.split('_', 1)
    if meta_prefix != config.get('meta_prefix'):
        msg = f'The prefix in the meta data sector was {meta_prefix}, however, expected is {config.get("meta_prefix")}.'
        raise UnexpectedMetaDataException(msg)

    if not flags_str.isdigit():
        msg = f'The suffix in the meta data sector is {flags_str}, however, expected is a digit.'
        raise UnexpectedMetaDataException(msg)

    # read more data from the other sectors
    flags = int(flags_str)
    username = _read_sector(sector=SECTOR_USERNAME, uid=uid, key=key)
    collmex_id = _read_sector(sector=SECTOR_COLLMEX_ID, uid=uid, key=key)
    password = _read_sector(sector=SECTOR_PASSWORD, uid=uid, key=key)
    print(f'Meta data: {meta_data}\nUsername: {username}\nCollmex ID: {collmex_id}')

    return {'uid': uid, 'username': username, 'collmex_id': collmex_id, 'password': password, 'flags': flags, 'meta_prefix': meta_prefix}


@sector_session(is_trailer_block=True)
def _set_sector_key(new_key, sector=None, uid=None, key=None):
    """
    Updates the authentication key for a single sector.

    Args:
        new_key (list[int] | bytes): New 6-byte key to set for the sector.
        sector (int): Sector number whose key is updated.
        uid (list[int] | None): UID of the RFID card.
        key (list[int] | None): 6-byte authentication key for the card.
            If not specified, default and custom keys are applied.

    Raises:
        ReadWriteFailureException: If updating the sector trailer fails.

    """
    new_key = _normalize_key(new_key)
    trailer_block = get_sector_trailer(sector)
    trailer = bytes(new_key + [0xFF, 0x07, 0x80, 0x69] + new_key)
    if reader.write(trailer_block, trailer) != reader.OK:
        msg = f'Failed to update the key for sector {sector}.'
        raise ReadWriteFailureException(msg)


@card_session
def set_key_for_all_sectors(new_key, uid=None, key=None):
    """
    Updates the authentication key for all application-specific sectors.

    Applies the new key to the metadata, username, Collmex ID,
    and password sectors.

    Args:
        new_key (list[int] | bytes): New 6-byte key to set for all sectors.
        uid (list[int] | None): UID of the RFID card.
        key (list[int] | None): 6-byte authentication key for the card.
            If not specified, default and custom keys are applied.

    """
    for isector in (SECTOR_META, SECTOR_USERNAME, SECTOR_COLLMEX_ID, SECTOR_PASSWORD):
        _set_sector_key(new_key, uid=uid, sector=isector, key=key)


async def open_cash_register():
    relay = Pin(13, Pin.OUT)
    relay.value(0)
    await asyncio.sleep_ms(300)
    relay.value(1)


def start_rfid_reading():
    asyncio.create_task(_rfid_reading())


async def _rfid_reading():
    store = AuthorizedRFIDStore()
    while True:
        try:
            rfid_data = await read_data()
            has_acccess_to_cash_register = rfid_data['flags'] & FLAG_CASH_REGISTER
            if has_acccess_to_cash_register and store.is_uid_registered(rfid_data['uid']):
                print(f'Key {rfid_data["uid"]} is authorized to open the cash register!')
                await open_cash_register()
                print()
        except NoCardDetectedException:
            pass  # silent
        except RFIDException as e:
            print(f'Failed to read the RFID tag: {e}\n')
        await asyncio.sleep_ms(250)
