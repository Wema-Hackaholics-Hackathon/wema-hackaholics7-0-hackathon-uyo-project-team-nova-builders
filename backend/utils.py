from uuid import uuid4

def customID() -> str:
    """Helper for generating custon FOID Ids"""
    rand_id = uuid4()
    string_id = str(rand_id)
    slice = string_id[8:13]
    new_id = f'FOID:USER{slice}'
    return new_id


def customKYCID() -> str:
    """Helper for generating custon FOID KYC Ids"""
    rand_id = uuid4()
    string_id = str(rand_id)
    slice = string_id[8:13]
    new_id = f'FOID:KYC{slice}'
    return new_id