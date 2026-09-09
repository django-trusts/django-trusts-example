"""Windows access-mask and SID constants used by the bounded evaluator.

Vectors and comments are documentation-derived until separately verified
against a Windows host. See docs/WINFS_ACL.md.
"""

# Depth is measured in parent links (approved r3 erratum).
#   target dist = 0
#   valid root may appear at dist = 64
#   expand while current dist < 64
#   overflow iff dist = 64 AND parent_id IS NOT NULL
# anc may emit distances 0..64 (65 nodes including the target).
MAX_PARENT_DEPTH = 64

# Operational ACE-bag limit for the reference PostgreSQL statement.
# Independent of MAX_PARENT_DEPTH; ACE count is not capped at 64.
MAX_ACE_SCAN = 4096

SID_CREATOR_OWNER = "S-1-3-0"
SID_OWNER_RIGHTS = "S-1-3-4"

KIND_FILE = "file"
KIND_FOLDER = "folder"
ACE_ALLOW = "allow"
ACE_DENY = "deny"

# Specific bits used by the V1–V43 matrix.
FILE_READ_DATA = 0x0001
FILE_LIST_DIRECTORY = 0x0001
FILE_WRITE_DATA = 0x0002
FILE_ADD_FILE = 0x0002
FILE_APPEND_DATA = 0x0004
FILE_READ_EA = 0x0008
FILE_WRITE_EA = 0x0010
FILE_EXECUTE = 0x0020
FILE_TRAVERSE = 0x0020
FILE_DELETE_CHILD = 0x0040
FILE_READ_ATTRIBUTES = 0x0080
FILE_WRITE_ATTRIBUTES = 0x0100

DELETE = 0x00010000
READ_CONTROL = 0x00020000
WRITE_DAC = 0x00040000
WRITE_OWNER = 0x00080000
SYNCHRONIZE = 0x00100000
STANDARD_RIGHTS_READ = READ_CONTROL
STANDARD_RIGHTS_WRITE = READ_CONTROL
STANDARD_RIGHTS_EXECUTE = READ_CONTROL
STANDARD_RIGHTS_REQUIRED = 0x000F0000

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_EXECUTE = 0x20000000
GENERIC_ALL = 0x10000000

# Request-side generic mapping (File Access Rights Constants).
# SYNCHRONIZE overlap is why GENERIC_WRITE can block GENERIC_READ.
FILE_GENERIC_READ = (
    STANDARD_RIGHTS_READ
    | FILE_READ_DATA
    | FILE_READ_ATTRIBUTES
    | FILE_READ_EA
    | SYNCHRONIZE
)
FILE_GENERIC_WRITE = (
    STANDARD_RIGHTS_WRITE
    | FILE_WRITE_DATA
    | FILE_WRITE_ATTRIBUTES
    | FILE_WRITE_EA
    | FILE_APPEND_DATA
    | SYNCHRONIZE
)
FILE_GENERIC_EXECUTE = (
    STANDARD_RIGHTS_EXECUTE
    | FILE_READ_ATTRIBUTES
    | FILE_EXECUTE
    | SYNCHRONIZE
)
FILE_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0x1FF

R = FILE_READ_DATA
W = FILE_WRITE_DATA
X = FILE_EXECUTE
RC = READ_CONTROL
WD = WRITE_DAC
LIST = FILE_LIST_DIRECTORY

GENERIC_BITS = GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE | GENERIC_ALL
MASK_32 = 0xFFFFFFFF


def map_generic_mask(desired_mask):
    """Expand GENERIC_* bits on the request. Stored ACEs hold specific bits only."""
    mapped = int(desired_mask) & MASK_32
    if mapped & GENERIC_READ:
        mapped |= FILE_GENERIC_READ
    if mapped & GENERIC_WRITE:
        mapped |= FILE_GENERIC_WRITE
    if mapped & GENERIC_EXECUTE:
        mapped |= FILE_GENERIC_EXECUTE
    if mapped & GENERIC_ALL:
        mapped |= FILE_ALL_ACCESS
    return mapped & ~GENERIC_BITS & MASK_32
