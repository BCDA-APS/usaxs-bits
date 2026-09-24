#!/APSshare/anaconda/x86_64/bin/python
#!/APSshare/epd/rh5-x86/bin/python
#!/usr/bin/env python

'''
Helper tool when configuring the EPICS areaDetector NeXus File plugin.

Copies EPICS PV configuration from the attributes file 
to a NXcollection group in the template file.
'''


import os
import sys
import argparse
import datetime

from xml.etree import ElementTree as etree
# We want lxml rather than ElementTree so we can use XPath to locate our elements
# BUT, lxml throws a core file when trying to open the attributes file 
# or parse its content from a string
#from lxml import etree
from xml.dom import minidom     # for prettyprinting


def get_PV_dict(filename):
    '''return a dict of EPICS PV declarations from the attributes file'''
    tree = etree.parse(filename)
    pv_dict = {}
    for attr_node in tree.getroot():
        if attr_node.tag == 'Attribute' \
            and 'type' in attr_node.attrib \
            and attr_node.attrib['type'] == 'EPICS_PV':
                d = {
                    'pv' : attr_node.attrib['source'],
                    'desc' : attr_node.attrib['description'],
                    'name' : attr_node.attrib['name']
                }
                pv_dict[ d['name'] ] = d
    return pv_dict


class NoNodesError(IndexError):
    '''no nodes were found'''
    def __init__(self, arg):
        self.args = arg


class MultipleNodesError(IndexError):
    '''multiple nodes were found'''
    def __init__(self, arg):
        self.args = arg


def open_one_subnode(parent, tag, filename):
    '''find and return a single node matching the tag, raise exceptions otherwise'''
    nodelist = parent.findall(tag)
    if len(nodelist) == 0:
        # FIXME: exception reporting looks off
        raise NoNodesError, "Need one " + tag + " node defined in " + filename
    if len(nodelist) > 1:
        # FIXME: exception reporting looks off
        raise MultipleNodesError, "Need _one_ " + tag + " node defined in " + filename
    return nodelist[0]


def add_XML_element(parent, tag, value = None, **alist):
    '''create an XML node and hang it on the tree'''
    node = etree.Element(tag)
    if value is not None:
        node.text = value
    for key in alist:
        node.attrib[key] = alist[key]
    parent.append(node)
    return node


def build_new_collection(parent, pv_dict):
    '''rebuild the NXcollection element'''
    # this is easy, create the NXcollection node
    # <NXcollection name="EPICS_PV_metadata" type="UserGroup">
    # <!-- !!! type="UserGroup" will not be needed in AD1.7 !!! -->
    iso8601 = "T".join(str(datetime.datetime.now()).split())
    nxcoll = add_XML_element(parent, "NXcollection", name="EPICS_PV_metadata", type="UserGroup")
    add_XML_element(nxcoll, "Attr", iso8601, name='modified', type="CONST")
    cmt = etree.Comment(''' !!! type="UserGroup" will not be needed in AD1.7 !!! ''')
    nxcoll.append( cmt )

    for name in sorted(pv_dict.keys()):
        node = add_XML_element(nxcoll, name, source=name, type="ND_ATTR")
        add_XML_element(node, "Attr", pv_dict[name]['pv'], name='pv', type="CONST")
        add_XML_element(node, "Attr", pv_dict[name]['desc'], name='description', type="CONST")


def pretty_print(tree):
    '''adds too much blank space to the view'''
    doc = minidom.parseString(tree)
    return doc.toprettyxml(indent = "  ")


def write_template_file(tree, filename):
    '''write the tree to an XML file'''
    # ElementTree does not put the XML line at the top of the file.
    #tree.write(filename)  
    # We'll put it there, and the SVN keyword block, as well.
    # A bit tricky here, write the SVN keyword block 
    # for the XML file, not this Python file
    header = '''<?xml version="1.0" encoding="UTF-8"?>

<!--
########### SVN repository information ###################
# %s: $
# %s: $
# %s: $
# %s: $
# %s: $
########### SVN repository information ###################
-->
    \n''' % ('$Date', '$Author', '$Revision', '$HeadURL', '$Id')
    f = open(filename, 'w')
    f.write(header)
    f.write(etree.tostring(tree.getroot()))
    f.close()


def main(attr_file, templ_file):
    '''
    rebuilds NXcollection element with subnodes of form::
    
      <transNosePD_Value_Spl source="transNosePD_Value_Spl" type="ND_ATTR">
        <Attr name="pv" type="CONST">15iddSAXS:transNosePD_Value_Spl</Attr>
        <Attr name="description" type="CONST">transNosePD_Value_Spl</Attr>
      </transNosePD_Value_Spl>

    '''
    pv_dict = get_PV_dict(attr_file)
    if len(pv_dict) == 0:
        raise Exception, attr_file + " had no Attribute elements"
    try:
        tree = etree.parse(templ_file)
    except:
        raise Exception, templ_file + " is not an XML file"
    root = tree.getroot()

    nxentry = open_one_subnode(root, 'NXentry', templ_file)
    try:
        # remove an existing NXcollection
        nxcoll = open_one_subnode(nxentry, 'NXcollection', templ_file)
        nxentry.remove(nxcoll)
    except NoNodesError:
        # this situation is fine, NXcollection will be created below
        pass
    
    build_new_collection(nxentry, pv_dict)
    write_template_file(tree, templ_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument('attributes_file', help='NeXus file plugin attributes XML file')
    parser.add_argument('template_file', help='NeXus file plugin template XML file')
    args = vars(parser.parse_args())
    attributes_file = args['attributes_file']
    template_file = args['template_file']

    main(attributes_file, template_file)


########### SVN repository information ###################
# $Date: 2015-02-25 13:13:08 -0600 (Wed, 25 Feb 2015) $
# $Author: jemian $
# $Revision: 8018 $
# $URL: https://subversion.xray.aps.anl.gov/bcdaioc/9idc_AD/area_detector/WAXS_config/copy_attributes_to_template.py $
# $Id: copy_attributes_to_template.py 8018 2015-02-25 19:13:08Z jemian $
########### SVN repository information ###################
