import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


class TestGimpStartupFlow:
    @pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
    def test_gimp_process_starts(self):
        # Arrange
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, error_output = gimp.version_return_code()

        # Assert
        assert return_code == 0, error_output