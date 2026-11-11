"""Locations of the official EET 2.0 files shipped with the module."""
import os

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA_XSD = os.path.join(MODULE_DIR, "data", "schema", "EETXMLSchema.xsd")
CA_DIR = os.path.join(MODULE_DIR, "data", "ca")
CA_SUB_PLAYGROUND = os.path.join(CA_DIR, "ca_eet-sub_cert-playground.crt")
CA_SUB_PRODUCTION = os.path.join(CA_DIR, "ca_eet-sub_prod.pem")

# Public Playground test data published by the Financial Administration.
TEST_DATA_DIR = os.path.join(MODULE_DIR, "tests", "data")
TEST_P12 = {
    eic: os.path.join(TEST_DATA_DIR, f"CA_EET-Playground-{eic}.p12")
    for eic in ("CZ00000019", "CZ683555118", "CZ8551015704")
}
TEST_P12_PASSWORD = b"aaaa1111"
