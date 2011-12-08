#!/usr/bin/python -OO
"""
Wikipedia for relationships between living people

INPUT:
    Wikipedia database XML datadump (http://en.wikipedia.org/wiki/Wikipedia:Database_download)

OUTPU:
    sqllite DB with tables: article and links. Optionally if scrip is invoked with option
    -i (--include-categories) - category and article_category table with all found categories
    and article link to categories.

STEPS

1st pass/phase (scans through all XML dump)
===========================================
1) Begin by identifying all articles about living people in the Wikipedia XML datadump
(articles that belong to the categroy "Living People").

2) For each of the identified parent articles in Step 1,
examines all links within the article to other child Wikipedia articles;

2nd pass/phase (scans through all XML dump)
===========================================
3) For each link in Step 2, determine which links reference articles about other living persons
and which article links do NOT (scanning through all aricles and parsing one identified as child articles)

"""
#-------------------------------------------------------------------------------
# Name:     load_wiki_xml_cat.py
# Purpose:
#     Loads Wikipedia "Living people" category article ursl and all child urls
#     and marks them as aricle about living perosn if the article belonging
#     to the category "Living people".
#
# Author:   Radomirs Cirskis
#
# Created:  2011-11-20
# Licence:  WTFPL
#-------------------------------------------------------------------------------

from xml.parsers import expat
import re
import sys
import urllib, os, os.path
import sqlite3
import argparse
import time
import json

# Constants:
version = '1.6'

# element/tag names:
tagPage = 'page'
tagTitle = 'title'
tagId = 'id'
tagText = 'text'
tagRevision = 'revision'
tagMediawiki = 'mediawiki'

# Default DB name:
default_db_name = 'wppages.sqlite '

# Pre-copiled regular expressions:
category_re = re.compile('\[\[Category:([^]]+)]', re.I )
# Links to the child pages:
child_re = re.compile( '\[\[(?!Category:)([^]]+)]]', re.I)

def print_timing(func):
    """
    Time a function using time.time() and the a @ function decorator
    """
    def wrapper(*arg,**keywords):
        t1 = time.time()
        res = func(*arg,**keywords)
        t2 = time.time()
        delta_s = (t2-t1)
        print '* Excution of "%s" took %0.3fms (%0.3fs, %0.3fmin)' \
            % (func.func_name, delta_s*1000.0, delta_s, delta_s/60 )
        return res
    return wrapper

def get_args():
    """
    Command argument parser

    Returns structure:
        args.category
        args.include_categories
        args.dry_run
        args.phase
        args.db
        args.input
    """
    parser = argparse.ArgumentParser(description='Wikipedia XML dump parser')
    parser.add_argument( '-c', '--category', help='Article category (default:"Living people")',
                                             default='Living people')
    parser.add_argument( '-i', '--include-categories', action='store_true', default=False,
                                             help='Include categories (defaul: no)')
    parser.add_argument( '-D', '--dry-run', action='store_true', default=False,
                                             help='Parse Wikipedia XML dump without sotring data into the DB (defaul: no)')
    parser.add_argument( '-p', '--phase',
                                             help='Processing phase (default: both)',
                                             default='both',
                                             choices=['1','first','2','second','3','both'] )
    parser.add_argument( '-d', '--db',
                                             help='sqlite database file name (default: wppages.sqlite)',
                                             default=default_db_name )
    parser.add_argument( '--version', action='version', version='%(prog)s '+version)
    parser.add_argument( 'input', help='Wikipedia XML dump file')

    args = parser.parse_args()
    return args

class WPParser:
    """
    Wikipedia XML DB backup dump parser
    """

    _db_name = None
    _chunk_size = 1
    _number_in_chunk = 0
    # Indicator that tells parser to skip the current page
    skip_current_page = False
    start_time = None

    def __init__(
            self,
            living_person_category = 'Living people',
            phase = 1,
            include_categories = False,
            dry_run = False,
            db_name = None ):
        """
        Constructor
        """

        if not(self._db_name) and not(db_name):
            self._db_name = default_db_name
        elif not(self._db_name):
            self._db_name = db_name

        self._init()

        self._dry_run = dry_run
        self._living_person_category = living_person_category
        self._include_categories = include_categories
        if phase==1 or phase=='first':
            self._phase = 1
        else:
            self._phase = 2

        # Selected category regex
        self._category_re = re.compile( '\[\Category:[^]]*'+living_person_category, re.I)

        self._total_page_count = 0
        self._total_page_count_float = .0


    def _init(self):
        """
        Constructor and reset commont part
        """
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
        self._parser = expat.ParserCreate()
        self._parser.buffer_text = True
        # Buffer 1Mb (default: 8Kb):
        self._parser.buffer_size = 1048576
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
    id         INTEGER PRIMARY KEY,
    name     TEXT        NOT NULL UNIQUE
);

-- DROP TABLE IF EXISTS article;
CREATE TABLE IF NOT EXISTS article (
    -- Internal ID:
    id                             INTEGER PRIMARY KEY,
    title                        TEXT NOT NULL UNIQUE,
    -- Wikipedia DB ID:
    page_id                    INTEGER NULL UNIQUE,
    -- Article is about a living person (deteced based on the category)
    is_living_person BOOLEAN NOT NULL DEFAULT FALSE,
    -- The most recently detected parent (parsed artilce with link to the page)
    parent_id                INTEGER NULL,
    parsed_at                DATETIME NULL
 );

-- DROP TABLE IF EXISTS article_category;
CREATE TABLE IF NOT EXISTS article_category (
    id                    INTEGER PRIMARY KEY,
    article_id    INTEGER NOT NULL,
    category_id INTEGER NOT NULL );
CREATE UNIQUE INDEX IF NOT EXISTS article_category_idx ON article_category(article_id, category_id);

-- DROP TABLE IF EXISTS link;
CREATE TABLE IF NOT EXISTS link (
    id                         INTEGER PRIMARY KEY,
    article_id         INTEGER NOT NULL,
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

    def db_execute( self, *args, **keywords):
        """
        DB SQL statement execution wrapper function
        if "--dry-run" option set, do nothing
        """
        if self._dry_run:
            return None
        if self._cur == None:
            self.cur()
        return self._cur.execute( *args, **keywords)

    def db_executemany(self, *args, **keywords):
        """
        DB SQL statement execution wrapper function for executemany
        if "--dry-run" option set, do nothing
        """
        if self._dry_run:
            return None
        if self._cur == None:
            self.cur()
        return self._cur.executemany( *args, **keywords)

    def get_article_id( self, title):
        """
        Finds article_id based on article tile
        """
        cur = self.db_execute(
            "SELECT id FROM article WHERE title=? AND parsed_at IS NOT NULL", ( title, ) )
        if not(cur):
            return None
        else:
            row = cur.fetchone()
        if row:
            return row[0]
        else:
            return None

    def reset(self):
        """
        Reset parser in order to parse subsequent documents
        """
        self.close()
        self._init()

    def feed(self, data):
        self._parser.Parse(data, 0)

    @print_timing
    def feed_file(self, file_name, phase=1):
        """
        Parse Wikipedia XML dump file "feeding"
        EXPAT XML parser
        """
        self.reset()
        self.start_timer()
        self._phase = phase
        if phase==1 or self._chunk_size==1:
            ( self._total_line_count, self._total_page_count ) = self.get_volume( file_name )
            self._total_page_count_float = float(self._total_page_count)
            print "Total %d lines and %d articles found in the file %s (size: %s KB)" % \
                ( self._total_line_count, self._total_page_count, file_name, os.path.getsize( file_name )/1024)
            self._chunk_size = max( self._total_page_count / 80, 1)
            print "One tick (#): %d articles processed" % self._chunk_size
        if phase==2:
            print "Second phase/pass started"
        self._file = open( file_name, mode='rb')
        self._parser.ParseFile( self._file)
        self._file.close()

    def close(self):
        """
        Close all resourece used for parsing
        """
        # self._parser.Parse("", 1) # end of data
        self.db().close()
        del self._cn
        del self._parser # get rid of circular references

    def start_tag_handler(self, tag, attrs):
        """
        Element opening/start XML tag "<tag>" handler
        """
        self._data_start = False
        if tag == tagPage:
            self._id = self._title = self._text = None
            self._page_count += 1
            self._number_in_chunk = self._page_count % self._chunk_size
        self._parent_tag = self._tag
        self._tag = tag

    def end_tag_handler(self, tag):
        """
        Element closing/end XML tag "</tag>" handler
        """
        if tag == tagTitle:
            self._title = self._data.strip()
            # We are skipping non-English page:
            self.skip_current_page = self.is_non_en( self._title)
        elif tag == tagId and self._parent_tag == tagPage:
            self._id = int( self._data.strip() )
        elif tag == tagPage:
            if not(self._number_in_chunk):
                self.refresh_progress_bar()
        elif tag == tagText:
            if not self.skip_current_page:
                self.parse_page()
        elif tag == tagMediawiki:
            self.refresh_progress_bar()
            # The end of XML dump file reached - do clean-up:
            self.db().commit()
            self.cur().close()
            print "\n%d articles processed." % self._page_count
            if not( self._dry_run):
                # if "--dry-run" option set, don't vacuum DB:
                print "Parsing complete! Please wait until DB compacting is finised..."
                self.db().execute('VACUUM')

        self._tag = self._parent_tag
        self._parent_tag = None

    def data_tag_handler(self, data):
        """
        Elments values handler
        """
        self._data = data

    def start_timer( self):
        """
        Starte or resete timer to track time of longrunning processes
        """
        self.start_time = time.time()

    def time_passed( self):
        """
        Time passed in seconds since last time the time was started of reset
        """
        if self.start_time == None:
            self.start_timer()
        return (time.time()-self.start_time)

    def time_delta_str( self, time_delta):
        """
        Time interval in seconds presentation in seconds, minutes, hours depending
        on the magnitude of the value
        """
        unit = 's'
        if time_delta > 100:
            time_delta = time_delta / 60
            unit = 'min'
        if time_delta > 100:
            time_delta = time_delta / 60
            unit = 'h'
        if time_delta > 100:
            time_delta = time_delta / 24
            unit = 'days'
        return "%.2f%s" % (time_delta, unit)

    def refresh_progress_bar( self):
        unit = 's'
        time_passed = self.time_passed()
        if time_passed > 0 and self._page_count > 0:
            eta = self._total_page_count * time_passed / self._page_count - time_passed
            eta = self.time_delta_str( eta ) if eta > 0. else '0'
        else:
            eta = 'N/A'
        time_passed_str = self.time_delta_str( time_passed)
        progress_percentage = ( 100.0 * self._page_count ) / self._total_page_count
        pbar_format_str = "\r%.1f%% in %s ETA: %s "+"#"*int(progress_percentage+0.999999)
        sys.stderr.write( pbar_format_str % ( progress_percentage, time_passed_str, eta) )

    def parse_page( self):
        """
        Parse page and store page metat-data in the DB:
            - title,
            - time when the pages was parsed,
            - indicator showing that the article is about a living person,
            - links to other pages,
            - optionally categories and links to the found categories.
        """
        # print "Parsing page %s\n" % self._title
        article_id = None
        if self._phase==2:
            article_id = self.get_article_id( self._title)
            # ignore if the page wasn't found at the first phase/pass or already parsed:
            if not(article_id):
                return

        self._text = self._data
        is_living_person = False
        categories = None
        if self._include_categories:
            categories = set([item.strip() for sublist in
                                            [ cat.split('|') for cat in category_re.findall( self._text)]
                                        for item in sublist])
            if categories:
                is_living_person = ( self._living_person_category in categories )
                self.db_executemany(
                    "INSERT OR IGNORE INTO category (name) VALUES (?)",
                    [ (c,) for c in    categories ] )
        elif self._category_re.search(self._text):
            is_living_person = True
        if not(is_living_person) and self._phase==1:
            # At the first pass ignore pages not belonging to "Living peple" category
            return
        if not(article_id):
            self.db_execute(
                "INSERT OR IGNORE INTO article (title,page_id,is_living_person,parsed_at) VALUES (?,?,?,datetime('now'))",
                ( self._title, self._id, is_living_person, ) )
            if not self._dry_run:
                article_id = self._cur.lastrowid
            if article_id == None:
                self.db_execute(
                    "UPDATE article SET is_living_person=?, page_id=?, parsed_at=datetime('now') WHERE title=?",
                    ( is_living_person, self._id, self._title, ) )
                if not self._dry_run:
                    article_id = self._cur.lastrowid
        else: # Phase #2
            self.db_execute(
                "UPDATE article SET is_living_person=?, page_id=?, parsed_at=datetime('now') WHERE id=?",
                ( is_living_person, self._id, article_id ) )
        assert article_id != None
        if self._include_categories and categories:
            self.db_executemany(
                """INSERT OR IGNORE INTO article_category (article_id,category_id)
                VALUES (?, (SELECT id FROM category WHERE name=?) )""",
                [ ( article_id, c,) for c in categories ] )
        children = set([ item for item in [item.strip() for sublist in
                                    [ cat.split('|') for cat in child_re.findall( self._text)]
                                for item in sublist ] if self.is_en(item) ])
        if children:
            if self._phase==1:
                # At the second pass, process only links to the "Living people" pages
                self.db_executemany(
                    "INSERT OR IGNORE INTO article (title) VALUES (?)",
                    [ (title,) for title in    children ] )
            # set up the article_id as the last detected page referencing the child:
            self.db_executemany(
                "UPDATE article SET parent_id=? WHERE title=?",
                [ (article_id, title) for title in    children ] )
            # collect all links in the article in the "link" table:
            self.db_execute(
                """INSERT OR IGNORE INTO link
                    (article_id, ref_article_id)
                    SELECT parent_id, id
                    FROM article
                    WHERE parent_id=?""", (article_id,))
        if not(self._number_in_chunk) and not(self._dry_run):
            self.db().commit()

    @print_timing
    def get_volume( self, file_name ):
        """
        Counts lines and page/article entries in
        the source file and store in the stat file for repeated runs
        If the stat file exists, read it
        """
        stats_file_name = os.path.splitext(file_name)[0]+'_stats.json'
        if    os.path.exists(stats_file_name):
            stat_file = open( stats_file_name, 'r')
            stats = json.load( stat_file)
            stat_file.close()
            line_count = stats['line_count']
            page_count = stats['page_count']
        else:
            line_count = 0
            page_count = 0
            line_substr_count = 0

            f = open( file_name, 'r')
            for line in f:
                line_count += 1
                pos = 0
                while pos < len(line):
                    c = line[pos]
                    if c not in [' ', '\t']: ## c !=' ' and c!='\t':
                        # count element <page> entries only if not space characer is '<'
                        # this approach has better performance the simle substring search
                        if c == '<' :
                            if '<page>' in line:
                                page_count += 1
                        break
                    pos += 1

            stats = { 'line_count': line_count, 'page_count': page_count }
            stat_file = open( stats_file_name, 'w')
            json.dump( stats, stat_file)
            f.close()
        return ( line_count, page_count,)

    def is_en( self, title):
        """
        Test if page is an English page.
        Page is considered to be English or of an unknow language, if:
            1) it doesn't have language code;
            or
            2) if it does have one, it is not 'en'
        """
        return len(title) < 3 or title[2]!=':' or title[0:3]=='en:'

    def is_non_en( self, title):
        """
        Test if page is NOT an English page.
        """
        return not self.is_en(title)


def main():
    """
    Invokes parsing process interactively if the scrip run from terminal
    """
    args = get_args()
    p = WPParser(
        living_person_category = args.category,
        include_categories = args.include_categories,
        dry_run = args.dry_run,
        db_name = args.db )
    if args.phase in ['first','both','1','3']:
        p.feed_file( args.input, phase=1 )
    if args.phase in ['second','both','2','3']:
        p.feed_file( args.input, phase=2 )
    pass

if __name__ == '__main__':
    main()
