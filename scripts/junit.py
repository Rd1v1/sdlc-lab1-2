"""Экспорт результатов unittest в JUnit XML для CI/CD."""
import time
import unittest
import xml.etree.ElementTree as ET


class JUnitResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def startTest(self, test):
        super().startTest(test)
        self.started = time.perf_counter()
        self.case = ET.Element('testcase', name=test.id(), classname=type(test).__name__)

    def stopTest(self, test):
        self.case.set('time', str(time.perf_counter() - self.started))
        self.cases.append(self.case)
        super().stopTest(test)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        ET.SubElement(self.case, 'failure').text = self._exc_info_to_string(err, test)

    def addError(self, test, err):
        super().addError(test, err)
        ET.SubElement(self.case, 'error').text = self._exc_info_to_string(err, test)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        ET.SubElement(self.case, 'skipped', message=reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            tag = 'failure' if issubclass(err[0], test.failureException) else 'error'
            ET.SubElement(self.case, tag, message=str(subtest)).text = self._exc_info_to_string(err, test)
