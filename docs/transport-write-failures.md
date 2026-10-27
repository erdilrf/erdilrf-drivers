# A partial command write is not a missing device reply

The injected `Transport.write(data)` contract returns the number of bytes accepted by the transport. The driver must check that count before waiting for a response. This applies to the documented LR1000E2-family command bytes in this repository; it does not establish compatibility with other models or interfaces.

`Rangefinder` now raises `OSError` if a transport does not report accepting the complete command. A response-waiting call stops before reading for a reply. The fire-and-forget `start_continuous()` and `ld_constant_on()` calls perform the same check without inventing an acknowledgement. Normal public method results are unchanged when the complete write is reported. Exceptions raised by the transport itself still propagate.

The driver performs one write attempt. It does not resend a short write or its remainder automatically. A prefix may already have been accepted or transmitted; the error does not mean that nothing was sent. Flushing receive data cannot recall those bytes. Recovery belongs to the caller and the exact transport/device protocol, rather than a blind command retry.

A complete transport byte count is also not a device acknowledgement or a successful measurement. Existing response, status and timeout handling remains separate. The change does not add a serial write deadline or make a blocking transport call interruptible.

From a source checkout, reproduce the focused offline regressions without installing pyserial:

```sh
PYTHONPATH=python/src python3 -B -m unittest discover -s python/tests -p test_transport_writes.py -v
```

The scripted transport reports accepting zero, three or seven bytes of a command. The tests require an immediate write error, no response reads after that write, and no second write. Separate cases cover continuous-start and constant-on/off command paths. These are synthetic software controls, not serial captures or hardware tests.

This maintenance change leaves frame encoding, checksums, protocol documents and package version unchanged. It does not validate physical timing, sensor behaviour, ROS/PX4 integration, other ERDILRF series, safety or certification.

Prepared with AI assistance for ERDILRF / ERDI LASER, affiliated with the referenced module manufacturer, ERDI TECH LTD.
