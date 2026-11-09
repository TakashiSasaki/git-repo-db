"""Bounded child checker. Parsing accepts only local NT/Turtle, never URLs."""

import importlib.metadata
import json
import sys


def deny_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
        raise RuntimeError("network access forbidden in schema checker")


sys.addaudithook(deny_network)
from pyshacl import validate  # noqa: E402
from rdflib import Graph  # noqa: E402

data = Graph().parse(data=open(sys.argv[1]).read(), format="nt")
shapes = Graph().parse(data=open(sys.argv[2]).read(), format="turtle")
conforms, report, text = validate(
    data,
    shacl_graph=shapes,
    inference="none",
    advanced=False,
    js=False,
    do_owl_imports=False,
    meta_shacl=True,
)
print(
    json.dumps(
        {
            "status": "pass" if conforms else "fail",
            "engine": {
                "pyshacl": importlib.metadata.version("pyshacl"),
                "rdflib": importlib.metadata.version("rdflib"),
                "inference": "none",
                "js": False,
                "imports": False,
            },
            "raw_report": report.serialize(format="turtle"),
            "reason": text,
        }
    )
)
