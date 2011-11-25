#!/usr/bin/env python -OO
"""TODO: module description"""
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
import urllib, os, os.path
import sqlite3
import argparse
import time

def print_timing(func):
  """
  Time a function using time.time() and the a @ function decorator
  """
  def wrapper(*arg,**keywords):
    t1 = time.time()
    res = func(*arg,**keywords)
    t2 = time.time()
    delta_s = (t2-t1)
    print '%s took %0.3f ms (%0.3fs, %0.3fmin)' % (func.func_name, delta_s*1000.0, delta_s, delta_s/60 )
    return res
  return wrapper

# Constants:
version = '1.0'
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
category_re = re.compile('Category:([^]]*)]', re.I )
# Links to the child pages:
child_re = re.compile( '\[\[(?!Category:)([^]]*)]]', re.I)

def get_args():
  """
  Command argument parser

  Returns structure:
    args.category
    args.input

  """
  parser = argparse.ArgumentParser(description='Wikipedia XML dump parser')
  parser.add_argument( '-c', '--category', help='Article category (default:"Living people")',
                       default='Living people')
  parser.add_argument( '-i', '--include-categories', action='store_true',
                       help='Include categories (defaul: no)')
  parser.add_argument( '-p', '--phase',
                       help='Processing phase (default: both)',
                       default='both',
                       choices=['1','first','2','second','3','both'] )
  parser.add_argument( '-d', '--db',
                       help='sqlite database file name (default: wppages.sqlite)',
                       default='wppages.sqlite' )
  parser.add_argument( '--version', action='version', version='%(prog)s '+version)
  parser.add_argument( 'input', help='Wikipedia XML dump file')

  args = parser.parse_args()
  return args

class WPParser:

  _db_name = None
  _chunk_size = 1
  _number_in_chunk = 0

  def __init__(
      self,
      living_person_category = 'Living people',
      phase = 1,
      include_categories = False,
      db_name = None ):

    if not(self._db_name) and not(db_name):
      self._db_name = 'wppages.sqlite'
    elif not(self._db_name):
      self._db_name = db_name

    self._init()

    self._living_person_category = living_person_category
    self._include_categories = include_categories
    if phase==1 or phase=='first':
      self._phase = 1
    else:
      self._phase = 2

    # Selected category regex
    self._category_re = re.compile( '\[\Category:[^]]*'+living_person_category, re.I)


  def _init(self):
    self._init_parser()
    # current element tag
    self._tag = None
    # Last parsed page subelemt values
    self._cur = self._cn = self._id = self._title = self._text = self._value = None
    self._page_count = 0
    self._data_start = False


  def _init_parser(self):
    """
    Instantiates EXPAT parser
    """
    self._parser = expat.ParserCreate(
      namespace_separator = xmlNsSeparator )
    self._parser.StartElementHandler = self.start_tag_handler
    self._parser.EndElementHandler = self.end_tag_handler
    self._parser.CharacterDataHandler = self.data_tag_handler

  def _initDb(self):
    """
    Instantiaes DB connections and builds all DB objects
    if they do not exist
    """
    self._cn = sqlite3.connect( self._db_name )
    self._cn.executescript("""
-- Setting for better sqlite performance:
PRAGMA encoding = "UTF-8";
PRAGMA page_size = 8192; -- 16384;
PRAGMA synchronous = OFF;
-- PRAGMA journal_mode = OFF;
PRAGMA journal_mode = MEMORY;
-- PRAGMA count_changes = OFF;
PRAGMA cache_size = 10000; -- Default: 2000
PRAGMA temp_store = MEMORY;
PRAGMA locking_mode=EXCLUSIVE;


-- DROP TABLE IF EXISTS category;
CREATE TABLE IF NOT EXISTS category (
  id     INTEGER PRIMARY KEY,
  name   TEXT    NOT NULL UNIQUE
);

-- DROP TABLE IF EXISTS article;
CREATE TABLE IF NOT EXISTS article (
  -- Internal ID:
  id               INTEGER PRIMARY KEY,
  title            TEXT NOT NULL UNIQUE,
  -- Wikipedia DB ID:
  page_id          INTEGER NULL UNIQUE,
  -- Article is about a living person (deteced based on the category)
  is_living_person BOOLEAN NOT NULL DEFAULT FALSE,
  -- The most recently detected parent (parsed artilce with link to the page)
  parent_id        INTEGER NULL,
  parsed_at        DATETIME NULL
 );

-- DROP TABLE IF EXISTS article_category;
CREATE TABLE IF NOT EXISTS article_category (
  id          INTEGER PRIMARY KEY,
  article_id  INTEGER NOT NULL,
  category_id INTEGER NOT NULL );
CREATE UNIQUE INDEX IF NOT EXISTS article_category_idx ON article_category(article_id, category_id);

-- DROP TABLE IF EXISTS link;
CREATE TABLE IF NOT EXISTS link (
  id             INTEGER PRIMARY KEY,
  article_id     INTEGER NOT NULL,
  ref_article_id INTEGER NOT NULL );
CREATE UNIQUE INDEX IF NOT EXISTS link_idx ON link(article_id, ref_article_id);
""")
    self._cn.commit()

  def db(self):
    """
    Lazy load of a single DB connection
    """
    if self._cn == None:
      self._initDb()
    return self._cn

  def cur(self):
    """
    Lazy load of a single DB cursor
    """
    if self._cur == None:
      self._cur = self.db().cursor()
    return self._cur

  def reset(self):
    """
    Reset parser in order to parse subsequent documents
    """
    self.close()
    self._init()

  def feed(self, data):
    self._parser.Parse(data, 0)

  @print_timing
  def feedFile(self, fileName, phase=1):
    """
    Observed performace: 35MiB (4338 articles) in 1:40
    Average size of an article: 8650
    """
    self.reset()
    self._phase = phase
    if phase==1 or self._chunk_size==1:
      ( self._total_line_count, self._total_page_count ) = self.get_volume( fileName )
      print "Total %d lines and %d articles found in the file %s (size: %s KB)" % \
        ( self._total_line_count, self._total_page_count, fileName, os.path.getsize( fileName )/1024)
      self._chunk_size = max( self._total_page_count / 80, 1)
      print "One tick (#): %d articles processed" % self._chunk_size
    if phase==2:
      print "Second phase/pass started"
    self._file = open( fileName, mode='rb')
    self._parser.ParseFile( self._file)
    self._file.close()

  def close(self):
    # self._parser.Parse("", 1) # end of data
    self.db().close()
    del self._cn
    del self._parser # get rid of circular references

  def start_tag_handler(self, tag, attrs):
    self._data_start = False
    if tag == tagPage:
      self._id = self._title = self._text = None
      self._page_count += 1
      self._number_in_chunk = self._page_count % self._chunk_size
    self._parent_tag = self._tag
    self._tag = tag

  def end_tag_handler(self, tag):
    if tag == tagTitle:
      self._title = self._data.strip()
    elif tag == tagId and self._parent_tag == tagPage:
      self._id = int( self._data.strip() )
    elif tag == tagPage:
      if not(self._number_in_chunk):
        sys.stderr.write('#')
      self.parse_page()
    elif tag == tagMediawiki:
      # The end of XML dump file reached - do clean-up:
      self.db().commit()
      self.cur().close()
      print "\n%d articles processed." % self._page_count
      print "Parsing complete! Please wait until DB compacting is finised..."
      self.db().execute('VACUUM')

    self._tag = self._parent_tag
    self._parent_tag = None

  def data_tag_handler(self, data):
    # dealing with data fragmentation (bug in expat parser)
    if not(self._data_start):
      self._data = ''
      self._data_start = True
    self._data += data

  def parse_page( self):
    """
    Parse page and store page metat-data in the DB
    """
    # print "Parsing page %s\n" % self._title

    article_id = None
    if self._phase==2:
      # ignore if the page wasn't found at the first phase/pass or already parsed:
      row = self.cur().execute(
        "SELECT id FROM article WHERE title=? AND parsed_at IS NOT NULL",
        (self._title, ) ).fetchone()
      if row:
        article_id = row[0]
      else:
        return

    self._text = self._data
    is_living_person = False
    categories = None
    if self._include_categories:
      categories = [item.strip() for sublist in
                      [ cat.split('|') for cat in category_re.findall( self._text)]
                    for item in sublist]
      if categories:
        is_living_person = ( self._living_person_category in categories )
        self.cur().executemany(
          "INSERT OR IGNORE INTO category (name) VALUES (?)",
          [ (c,) for c in  categories ] )
    elif self._category_re.search(self._text):
      is_living_person = True
    if not(is_living_person) and self._phase==1:
      # At the first pass ignore pages not belonging to "Living peple" category
      return
    if not(article_id):
      self.cur().execute(
        "INSERT OR IGNORE INTO article (title,page_id,is_living_person,parsed_at) VALUES (?,?,?,datetime('now'))",
        ( self._title, self._id, is_living_person, ) )
      article_id = self._cur.lastrowid
      if article_id == None:
        self._cur.execute(
          "UPDATE article SET is_living_person=?, page_id=?, parsed_at=datetime('now') WHERE title=?",
          ( is_living_person, self._id, self._title, ) )
        article_id = self._cur.lastrowid
    else: # Phase #2
        self._cur.execute(
          "UPDATE article SET is_living_person=?, page_id=?, parsed_at=datetime('now') WHERE id=?",
          ( is_living_person, self._id, article_id ) )
    assert article_id != None
    if self._include_categories and categories:
      self._cur.executemany(
        """INSERT OR IGNORE INTO article_category (article_id,category_id)
        VALUES (?, (SELECT id FROM category WHERE name=?) )""",
        [ ( article_id, c,) for c in categories ] )
    children = [item.strip() for sublist in
                  [ cat.split('|') for cat in child_re.findall( self._text)]
                for item in sublist]
    if children:
      if self._phase==1:
        # At the second pass, process only links to the "Living people" pages
        self._cur.executemany(
          "INSERT OR IGNORE INTO article (title) VALUES (?)",
          [ (title,) for title in  children ] )
      # set up the article_id as the last detected page referencing the child:
      self._cur.executemany(
        "UPDATE article SET parent_id=? WHERE title=?",
        [ (article_id, title) for title in  children ] )
      # collect all links in the article in the "link" table:
      self._cur.execute(
        """INSERT OR IGNORE INTO link
          (article_id, ref_article_id)
          SELECT parent_id, id
          FROM article
          WHERE parent_id=?""", (article_id,))
    if not(self._number_in_chunk):
      self.db().commit()

  def get_volume( self, file_name ):
    """
    Counts lines and page/article entries in
    the source file
    """

    line_count = 0
    page_count = 0
    line_substr_count = 0

    f = open( file_name, 'r')
    for line in f:
      line_count += 1
      if line.find( '<page>') >= 0:
        page_count += 1

    f.close()
    return ( line_count, page_count,)


def main():
  args = get_args()
  p = WPParser(
    living_person_category = args.category,
    include_categories = args.include_categories,
    db_name = args.db )
  #if not( os.path.exists( source_file_name) ):
  #  print >> sys.stderr, "Downloading %s ... Please wait!" % source_url
  #  urllib.urlretrieve( source_url, source_file_name )
  #if not( os.path.exists( proto_source_file_name) ):
  #  print >> sys.stderr, "Downloading %s ... Please wait!" % proto_source_url
  #  urllib.urlretrieve( proto_source_url, proto_source_file_name )
  if args.phase in ['first','both','1','3']:
    p.feedFile( args.input, phase=1 )
  if args.phase in ['second','both','2','3']:
    p.feedFile( args.input, phase=2 )
  pass

if __name__ == '__main__':
  main()

