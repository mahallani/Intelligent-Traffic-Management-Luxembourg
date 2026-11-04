"""A second collector on the same output file must be refused; the lock is released at exit."""
import pytest

from single_instance import AlreadyRunning, SingleInstance


def test_second_instance_refused_and_lock_released(tmp_path):
    target = tmp_path / "cita_traffic_sites_v2.csv"
    with SingleInstance(target):
        with pytest.raises(AlreadyRunning):
            SingleInstance(target).__enter__()
    with SingleInstance(target):        # released: a restart works
        pass
