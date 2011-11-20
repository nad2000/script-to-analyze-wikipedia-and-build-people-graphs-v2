#-------------------------------------------------------------------------------
# Name:        load_wiki_xml_cat.py
# Purpose:
#   Loads Wikipedia "Living people" category article ursl and all child urls
#   and marks them belonging to the category.
#
# Author:      Radomirs Cirskis
#
# Created:     2011-11-20
# Licence:     WTFPL
#-------------------------------------------------------------------------------
#!/usr/bin/env python

from xml.parsers import expat
import re
import sys
import urllib, os

iana_url = 'http://www.iana.org/assignments'

source_file_name = 'service-names-port-numbers.xml'
source_url = iana_url+'/service-names-port-numbers/'+source_file_name

proto_source_file_name = 'protocol-numbers.xml'
proto_source_url = iana_url+'/protocol-numbers/'+proto_source_file_name


# import sqlite3

# Constants
nsASS = iana_url
xmlnsSeparator = '#'

# element/tag names:

tagRecord = nsASS+xmlnsSeparator+'record'
tagProtocol = nsASS+xmlnsSeparator+'protocol'
tagXref = nsASS+xmlnsSeparator+'xref'
tagDescription = nsASS+xmlnsSeparator+'description'
tagNumber = nsASS+xmlnsSeparator+'number'
tagName = nsASS+xmlnsSeparator+'name'
tagRegistry = nsASS+xmlnsSeparator+'registry'
tagValue = nsASS+xmlnsSeparator+'value'

# REs:
port_range_re = re.compile('(\d{1,6})-(\d{1,6})')
stip_re = re.compile('reserved|unassigned', re.I)

# protocols:

protocols = {
    'hopopt': 0, 'icmp': 1,     'igmp': 2,      'ggp': 3, 'ip': 4,      'st': 5,        'tcp': 6,       'cbt': 7,       'egp': 8,
    'igp': 9, 'bbn-rcc-mon': 10,        'nvp-ii': 11,   'pup': 12,      'argus': 13,    'emcon': 14,    'xnet': 15,
    'chaos': 16, 'udp': 17,     'mux': 18,      'dcn-meas': 19, 'hmp': 20,      'prm': 21,      'xns-idp': 22,  'trunk-1': 23,
    'trunk-2': 24, 'leaf-1': 25,        'leaf-2': 26,   'rdp': 27,      'irtp': 28,     'iso-tp4': 29,  'netblt': 30,
    'mfe-nsp': 31,      'merit-inp': 32,        'dccp': 33,     '3pc': 34,      'idpr': 35,     'xtp': 36,      'ddp': 37,
    'idpr-cmtp': 38,    'tp++': 39,     'il': 40,       'ipv6': 41,     'sdrp': 42,     'ipv6-route': 43,       'ipv6-frag': 44,
    'idrp': 45, 'rsvp': 46,     'gre': 47,      'mhrp': 48,     'bna': 49,      'esp': 50,      'ah': 51,       'i-nlsp': 52,
    'swipe': 53, 'narp': 54,    'mobile': 55,   'tlsp': 56,     'skip': 57,     'ipv6-icmp': 58,        'ipv6-nonxt': 59,
    'ipv6-opts': 60, 'cftp': 62,        'sat-expak': 64,        'kryptolan': 65,        'rvd': 66,
    'ippc': 67, 'sat-mon': 69,  'visa': 70,     'ipcv': 71,     'cpnx': 72,     'cphb': 73,     'wsn': 74,      'pvp': 75,
    'br-sat-mon': 76, 'sun-nd': 77,     'wb-mon': 78,   'wb-expak': 79, 'iso-ip': 80,   'vmtp': 81,
    'secure-vmtp': 82, 'vines': 83,     'ttp': 84,      'iptm': 84,     'nsfnet-igp': 85,       'dgp': 86,      'tcf': 87,
    'eigrp': 88, 'ospf': 89,    'sprite-rpc': 90,       'larp': 91,     'mtp': 92,      'ax.25': 93,    'ipip': 94,
    'micp': 95, 'scc-sp': 96,   'etherip': 97,  'encap': 98, 'gmtp': 100,       'ifmp': 101,
    'pnni': 102, 'pim': 103,    'aris': 104,    'scps': 105,    'qnx': 106,     'a/n': 107,     'ipcomp': 108,
    'snp': 109, 'compaq-peer': 110,     'ipx-in-ip': 111,       'vrrp': 112,    'pgm': 113,     'l2tp': 115,
    'ddx': 116, 'iatp': 117,    'stp': 118,     'srp': 119,     'uti': 120,     'smp': 121,     'sm': 122,      'ptp': 123,
    'fire': 125, 'crtp': 126,   'crudp': 127,   'sscopmce': 128,        'iplt': 129, 'sps': 130,        'pipe': 131,
    'sctp': 132, 'fc': 133, 'manet': 138,       'hip': 139,     'shim6': 140 }

class ASSParser:
    def __init__(self):
        self._init_parser()

        # current element tag
        self._tag = None
        # Port or protocol registry
        self._is_port_doc = \
        self._protocol = self._name = self._description = self._number = None

        self._rec_count = 0
        self._data_start = False


    def _init_parser(self):
        self._parser = expat.ParserCreate(
            namespace_separator = xmlnsSeparator )
        self._parser.StartElementHandler = self.start
        self._parser.EndElementHandler = self.end
        self._parser.CharacterDataHandler = self.data


    def reset(self):
        """ Reste parser in order to parse subsequent documents """
        self.close()
        self.__init__()

    def feed(self, data):
        self._parser.Parse(data, 0)

    def feedFile(self, fileName):
        self._file= open( fileName, mode='rb')
        self._parser.ParseFile( self._file)
        self._file.close()

    def close(self):
        # self._parser.Parse("", 1) # end of data
        del self._parser # get rid of circular references

    def start(self, tag, attrs):
        self._data_start = False
        if tag == tagRecord:
            self._number = self._protocol = None
            self._name = self._description =  ''
        # Document root
        elif tag == tagRegistry:
            self._tag = self._protocol = self._name = self._description = self._number = self._value = None
            self._rec_count = 0
            self._is_port_doc = ( attrs['id'] == 'service-names-port-numbers' )
        if tag in [ tagProtocol, tagDescription, tagNumber, tagName, tagRecord]:
            self._tag = tag
        else:
            self._tag = None

    def print_value_line( self, line ):
        """ print INSERT statement value line and keep track of the processed records """
        if self._rec_count != 0:
            print ",\n",
        sys.stdout.write( line)
        self._rec_count += 1


    def end(self, tag):
        self._data_start = False
        if tag == tagRecord and ( self._number != None or self._value != None):
            if self._description == None or self._description == '' or stip_re.search( self._description ):
                return
            #print >>sys.stderr, tag, self._data
            self._description = self._description.strip()
            if self._rec_count == 0:
                if self._is_port_doc:
                    print 'INSERT INTO iana_ports ( port, protocol, name, description ) VALUES '
                else:
                    print 'INSERT INTO iana_protocols ( protocol, name, description ) VALUES '
            if self._is_port_doc:
                if self._number != None and '-' in self._number: # range
                    grps = port_range_re.match( self._number )
                    number_range = range( int(grps.group(1)), int(grps.group(2)) )
                else:
                    number_range = [self._number]
                if self._protocol in protocols:
                    protocol = protocols[self._protocol]
                else:
                    protocol = 255 # Unknown
                for number in number_range:
                    self.print_value_line( "  (%s,%s,'%s','%s')" % ( number, protocol, self._name, self._description ) )
            else:
                self.print_value_line( "  (%s,'%s','%s')" % ( self._value, self._name, self._description ) )
        elif tag == tagProtocol:
            self._protocol = self._data
        elif tag == tagDescription:
            self._description = self._data.replace("'","''")
        elif tag == tagNumber:
            self._number = self._data
        elif tag == tagName:
            self._name = self._data
        elif tag == tagValue:
            self._value = self._data
        elif tag == tagRegistry:
            print ';\n'


    def data(self, data):

        # dealing with data fragmentation
        if not(self._data_start):
            self._data = ''
            self._data_start = True

        self._data += data

def main():
    p = ASSParser()
    if not( os.path.exists( source_file_name) ):
        print >> sys.stderr, "Downloading %s ... Please wait!" % source_url
        urllib.urlretrieve( source_url, source_file_name )
    if not( os.path.exists( proto_source_file_name) ):
        print >> sys.stderr, "Downloading %s ... Please wait!" % proto_source_url
        urllib.urlretrieve( proto_source_url, proto_source_file_name )
    p.feedFile( proto_source_file_name)
    p.reset()
    p.feedFile( source_file_name)
    p.close()
    pass

if __name__ == '__main__':
    main()

