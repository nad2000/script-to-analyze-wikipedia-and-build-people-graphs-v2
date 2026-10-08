:
sqlite3 -header -batch -csv -separator ',' $1 <<"EOF"
PRAGMA encoding = "UTF-8";
PRAGMA page_size = 8192; -- 16384;
PRAGMA synchronous = OFF;
-- PRAGMA journal_mode = OFF;
PRAGMA journal_mode = MEMORY;
-- PRAGMA count_changes = OFF;
PRAGMA cache_size = 10000; -- Default: 2000
PRAGMA temp_store = MEMORY;
-- VACUUM;
ANALYZE;
.header on
.mode csv
-- Exporting external links:
SELECT 'Exporting external links...'
.echo OFF
.output links.csv
SELECT
  'http://en.wikipedia.org/wiki/'||REPLACE(a.title,' ','_') AS wikipedia_url,
  e.href AS external_link
FROM  external_link AS e JOIN article AS a ON a.id = e.article_id;
.output stdout
.echo ON
-- Exporting direct relationships:
SELECT 'Exporting direct relationships...'
.echo OFF
.output direct_relationships.csv
SELECT * FROM direct_relation;
.output stdout
.echo ON
SELECT 'Exporting indirect relationships...'
.echo OFF
.output indirect_relationships.csv
SELECT * FROM indirect_relation;
.output stdout
.echo ON
EOF
echo DONE...
