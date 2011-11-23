#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Name:    load_wiki_xml_cat.py
# Purpose:
#   Loads Wikipedia "Living people" category article ursl and all child urls
#   and marks them belonging to the category.
#
# Author:    Radomirs Cirskis
#
# Created:   2011-11-20
# Licence:   WTFPL
#-------------------------------------------------------------------------------

from xml.parsers import expat
import re
import sys
import urllib, os
import sqlite3
import argparse

# Constants:
# Wikipedia XML dump namespace:
xmlNs = "http://www.mediawiki.org/xml/export-0.5/"
xmlNsSeparator = '#'

# element/tag names:

tagPage = xmlNs+xmlNsSeparator+'page'
tagTitle = xmlNs+xmlNsSeparator+'title'
tagId = xmlNs+xmlNsSeparator+'id'
tagText = xmlNs+xmlNsSeparator+'text'
tagRevision = xmlNs+xmlNsSeparator+'revision'
tagMediawiki = xmlNs+xmlNsSeparator+'mediawiki'


# Pre-copiled regular expressions:
category_re = re.compile('Category:([^]]*)]', re.M|re.I )
# Links to the child pages:
child_re = re.compile( '\[\[(?!Category:)([^]]*)]]', re.M|re.I)

def get_args():
  """
  Command argument parser

  Returns structure:
    args.category
    args.input

  """
  parser = argparse.ArgumentParser(description='Wikipedia XML dump parser')
  parser.add_argument( '-c', '--category', help='Article category', default='Living people')
  parser.add_argument( 'input', help='Wikipedia XML dump file')

  args = parser.parse_args()
  return args

class WPParser:

  def __init__(self, living_person_category = 'Living people'):
    self._init_parser()

    # current element tag
    self._tag = None
    # Last parsed page subelemt values
    self._cur = self._cn = self._id = self._title = self._text = self._value = None

    self._living_person_category = living_person_category

    self._page_count = 0
    self._data_start = False

  def _init_parser(self):
    self._parser = expat.ParserCreate(
      namespace_separator = xmlNsSeparator )
    self._parser.StartElementHandler = self.start
    self._parser.EndElementHandler = self.end
    self._parser.CharacterDataHandler = self.data

  def _initDb(self):
    self._cn = sqlite3.connect('wppages4.sqlite')
    self._cn.executescript("""
-- DROP TABLE IF EXISTS category;
CREATE TABLE IF NOT EXISTS category (
    id        INTEGER PRIMARY KEY,
    name      TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS category_name_idx ON category(name);

-- DROP TABLE IF EXISTS article;
CREATE TABLE IF NOT EXISTS article (
    id      INTEGER PRIMARY KEY,
    title   TEXT NOT NULL,
    is_living_person BOOLEAN NOT NULL DEFAULT FALSE,
    parent_id INTEGER NULL,
    parsed_at DATETIME NULL
 );
CREATE UNIQUE INDEX IF NOT EXISTS article_title_idx ON article(title);

-- DROP TABLE IF EXISTS article_category;
CREATE TABLE IF NOT EXISTS article_category (
    article_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY(article_id,category_id) );
""")
    self._cn.commit()

  def db(self):
    if self._cn == None:
      self._initDb()
    return self._cn

  def cur(self):
    if self._cur == None:
      self._cur = self.db().cursor()
    return self._cur

  def reset(self):
    "Reste parser in order to parse subsequent documents"
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
    if tag == tagPage:
      self._id = self._title = self._text = None
      ++self._page_count
    self._parent_tag = self._tag
    self._tag = tag

  def end(self, tag):
    if tag == tagTitle:
      self._title = self._data.strip()
    elif tag == tagPage:
      # print "Parsing page %s\n" % self._title
      self._text = self._data
      # [item for sublist in l for item in sublist]
      categories = [item.strip() for sublist in
                      [ cat.split('|') for cat in category_re.findall( self._text)]
                    for item in sublist]
      if categories:
        is_living_person = ( self._living_person_category in categories )
        self.cur().executemany(
          "INSERT OR IGNORE INTO category (name) VALUES (?)",
          [ (c,) for c in  categories ] )
      else:
        is_living_person = False
      if is_living_person:
        self.cur().execute(
          "INSERT OR REPLACE INTO article (title,is_living_person,parsed_at) VALUES (?,1,datetime('now'))",
          ( self._title, ) )
      else:
        self._cur.execute(
          "INSERT OR IGNORE INTO article (title,is_living_person,parsed_at) VALUES (?,0,NULL)",
          ( self._title, ) )
      if categories:
        # TODO: pageID - to boost performance
        self._cur.executemany(
          """INSERT OR IGNORE INTO article_category (article_id,category_id)
          VALUES (
            (SELECT id FROM article WHERE title=?),
            (SELECT id FROM category WHERE name=?)
          )""",
          [ ( self._title, c) for c in categories ] )
      children = [item.strip() for sublist in
                    [ cat.split('|') for cat in child_re.findall( self._text)]
                  for item in sublist]
      if children:
        # TODO: Parent pageID:
        self.cur().executemany(
          "INSERT OR REPLACE INTO category (name) VALUES (?)",
          [ (c,) for c in  children ] )
      self.db().commit()
    elif tag == tagMediawiki:
      self.cur().close()

    self._tag = self._parent_tag
    self._parent_tag = None

  def data(self, data):
    # dealing with data fragmentation (bug in expat parser)
    if not(self._data_start):
      self._data = ''
      self._data_start = True

    self._data += data


def main():
  args = get_args()
  p = WPParser(living_person_category = args.category)
  #if not( os.path.exists( source_file_name) ):
  #  print >> sys.stderr, "Downloading %s ... Please wait!" % source_url
  #  urllib.urlretrieve( source_url, source_file_name )
  #if not( os.path.exists( proto_source_file_name) ):
  #  print >> sys.stderr, "Downloading %s ... Please wait!" % proto_source_url
  #  urllib.urlretrieve( proto_source_url, proto_source_file_name )
  p.feedFile( args.input )
  pass

if __name__ == '__main__':
  main()

