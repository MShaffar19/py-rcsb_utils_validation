##
# File:    ValidationReportReader.py
# Author:  J. Westbrook
# Date:    24-Jan-2019
# Version: 0.001
#
# Update:
#
#
##
"""
Various utilities for extracting data wwPDB validation report data
and transforming these data into mmCIF objects/files.

"""

import gzip
import logging
import operator
import time

from mmcif.api.DataCategory import DataCategory
from mmcif.api.PdbxContainers import DataContainer

from rcsb.utils.io.MarshalUtil import MarshalUtil
from rcsb.utils.validation.ValidationReportSchemaUtils import ValidationReportSchemaUtils

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class ValidationReportReader(object):
    """Various utilities for extracting data wwPDB validation report data
       and transforming these data into mmCIF objects/files.
    """

    def __init__(self, schemaMapPath):
        vrsu = ValidationReportSchemaUtils()
        self.__schemaMap = vrsu.fetchSchemaMap(schemaMapPath)
        self.__atOrdD = vrsu.getAttributeOrder()
        self.__atMap = vrsu.getAttributeMap()
        self.__attribD = {}
        for (catName, atName) in self.__schemaMap['attributes']:
            self.__attribD.setdefault(catName, []).append(atName)
        self.__mU = MarshalUtil()

    def read(self, xmlFilePath):
        """ Read input XML validation report data file and return data
            transformed mmCIF container objects.
        """
        xrt = self.__parse(xmlFilePath)
        rD = self.__extract(xrt)
        myContainerList = self.__buildCif(rD)
        return myContainerList

    def cnv(self, xmlfilePath, cifFilePath):
        """Read input XML validation report data file and return data
           transformed mmCIF container objects.

        Args:
            xmlfilePath (str): input XML validation report data file path
            cifFilePath (str): output mmCIF data file

        Returns:
            True for success or False otherwise
        """
        cL = self.read(xmlfilePath)
        ok = self.__mU.doExport(cifFilePath, cL, format="mmcif")
        return ok

    def __buildCif(self, rD, containerName='vrpt'):
        """ Construct a mmCIF data category objects for the input
            extracted data.

        Args:
            rD (dict): extracted data organized by category.
            containerName (str) : data block name

        Returns:
            containers (list):  data container list
        """
        #
        curContainer = DataContainer(containerName)
        for elName in rD:
            catName = elName
            if ((len(rD[elName]) < 1) or (len(self.__attribD[catName]) < 1) or (catName in ['programs'])):
                continue
            hasOrdinal = 'ordinal' in self.__attribD[catName]
            rowList = rD[elName]
            # Find the unique attribute content across the rowlist and the ordinal value
            atS = set()
            for ii, rowD in enumerate(rowList, 1):
                if hasOrdinal:
                    rowD['ordinal'] = ii
                if 'icode' in rowD:
                    rowD['icode'] = str(rowD['icode']).strip()
                if 'altcode' in rowD:
                    rowD['altcode'] = str(rowD['altcode']).strip()
                atS.update(rowD.keys())
            attributeNameList = list(atS)
            #
            # Set a reasonable order for these attributes
            #
            sD = {ky: self.__atOrdD[ky] for ky in attributeNameList}
            srtAtL = [tup[0] for tup in sorted(sD.items(), key=operator.itemgetter(1))]
            logger.debug("Category %s sorted attributes %r" % (catName, srtAtL))

            aCat = DataCategory(catName, srtAtL, rowList)
            curContainer.append(aCat)
        #
        # Adjust schema names -
        #
        atD = self.__schemaMap['attributes']
        for catName in curContainer.getObjNameList():
            catObj = curContainer.getObj(catName)
            atNameList = catObj.getAttributeList()
            mapD = {}
            mapCatName = self.__schemaMap['categories'][catName] if catName in self.__schemaMap[
                'categories'] else catName
            for atName in atNameList:
                mapD[atName] = atD[(catName, atName)]['at'] if (catName, atName) in atD else atName
            catObj.renameAttributes(mapD)
            catObj.setName(mapCatName)
        #
        # Map provenance items from programs.properties -
        #
        catObj = curContainer.getObj('program')
        if catObj and catObj.hasAttribute('properties'):
            for iRow in range(catObj.getRowCount()):
                pV = catObj.getValue('properties', iRow)
                pVL = [v.strip() for v in pV.split(',')]
                nL = [self.__atMap[ky] if ky in self.__atMap else ky for ky in pVL]
                catObj.setValue(",".join(nL), 'properties', iRow)
                # logger.info("Row %r properties %r" % (iRow, pV))
            return [curContainer]

    def __extract(self, xrt):
        """ Extract data from the input document and return a dictionary
            of categories containing rows of dictionaries with attribute naming.

        Args:
            xrt: ElementTree root element

        Returns:
            Extracted data (dict): dictionary organized by category with
                                   XML native data names.
        """
        atL = ['altcode', 'chain', 'ent', 'model', 'resname', 'resnum', 'said', 'seq']
        rD = {}
        for el in xrt.getroot():
            logger.debug("-- Element tag %r attrib count %r" % (el.tag, len(el.attrib)))
            rD.setdefault(el.tag, []).append(el.attrib)
            #
            msgD = el.attrib if el.tag == 'ModelledSubgroup' else {}
            # for ch in el.getiterator(tag=None):
            for ch in el:
                logger.debug("-- --> child element tag %r attrib count %r" % (ch.tag, len(ch.attrib)))
                # add parent cardinal attributes at residue level
                d = {k: ch.attrib[k] for k in ch.attrib}
                d.update({k: msgD[k] for k in atL if k in msgD})
                rD.setdefault(ch.tag, []).append(d)
                logger.debug("-- --> child element tag %r attrib count %r" % (ch.tag, len(d)))
                #
                for gch in ch:
                    logger.debug(
                        "-- -- --> grand child element tag %r attrib count %r" % (gch.tag, len(gch.attrib)))
                    # add parent cardinal attributes
                    rD.setdefault(gch.tag, []).append(gch.attrib)
        return rD
        #

    def __parse(self, filePath):
        """ Parse the input XML data file and return ElementTree root element.
        """
        tree = []
        if filePath[-3:] == '.gz':
            with gzip.open(filePath, mode='rb') as ifh:
                logger.debug('Parsing %s', filePath)
                t = time.time()
                tree = ET.parse(ifh)
                logger.debug('Parsed %s %.2f seconds' % (filePath, time.time() - t))
        else:
            with open(filePath, mode='rb') as ifh:
                logger.debug('Parsing %s', filePath)
                t = time.time()
                tree = ET.parse(ifh)
                logger.debug('Parsed %s in %.2f seconds' % (filePath, time.time() - t))
        return tree

    # -
    def __traverse(self, xrt, ns):
        """ Internal routine to traverse the dom covering/logging all elements and attributes.

        Args:
            xrt (object): ElementTree root element
            ns (str): XML namespace

        """

        for el in xrt.getroot():
            pEl = el.tag.replace(ns, "")
            logger.info("-- %r %r" % (pEl, el.attrib))
            for ch in el:
                chEl = ch.tag.replace(ns, "")
                logger.info("-- -->  %r %r" % (chEl, ch.attrib))
                if ch.text is not None and not len(ch.text):
                    logger.info("-- -->  %s" % ch.text)
                for gch in ch:
                    gchEl = gch.tag.replace(ns, "")
                    logger.info("-- -- -->  %r %r" % (gchEl, gch.attrib))
                    if gch.text is not None and not len(gch.text):
                        logger.info("-- -- -->  %s" % gch.text)
                    for ggch in gch:
                        ggchEl = ggch.tag.replace(ns, "")
                        logger.info("-- -- -- -->  %r %r" % (ggchEl, ggch.attrib))
                        if ggch.text is not None and not len(ggch.text):
                            logger.info("-- -- -- -->  %s" % ggch.text)
                        for gggch in ggch:
                            gggchEl = gggch.tag.replace(ns, "")
                            logger.info("-- -- -- -- -->  %r %r" % (gggchEl, gggch.attrib))
                            if gggch.text is not None and not len(gggch.text):
                                logger.info("-- -- -- -- -->  %s" % gggch.text)
