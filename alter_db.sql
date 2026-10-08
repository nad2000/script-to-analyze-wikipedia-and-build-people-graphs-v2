DROP VIEW IF EXISTS direct_relation;
DROP VIEW IF EXISTS _direct_relation;
DROP TABLE IF EXISTS direct_relation;
DROP TABLE IF EXISTS _direct_relation;

DROP VIEW IF EXISTS _indirect_relation;
DROP VIEW IF EXISTS indirect_relation;
DROP TABLE IF EXISTS _indirect_relation;
DROP TABLE IF EXISTS indirect_relation;

CREATE VIEW IF NOT EXISTS _direct_relation
AS
SELECT
    'http://en.wikipedia.org/wiki/'||REPLACE(s_title,' ','_') AS wikipedia_url_source,
    'http://en.wikipedia.org/wiki/'||REPLACE(t_title,' ','_') AS wikipedia_url_target,
    'http://en.wikipedia.org/wiki/'||REPLACE(s_title,' ','_') AS wikipedia_url_connection,
    'DIRECT' AS  relationship_type
FROM (
SELECT s.title AS s_title, t.title AS t_title
FROM article AS s JOIN link AS l ON l.article_id = s.id AND s.is_living_person
    AND l.article_id <> l.ref_article_id
  JOIN article AS t ON t.id = l.ref_article_id AND t.is_living_person
  ORDER BY 1,2 );

CREATE TABLE IF NOT EXISTS direct_relation AS SELECT * FROM _direct_relation WHERE 0=1;

-- DELETE FROM  direct_relation;
INSERT INTO direct_relation SELECT * FROM _direct_relation;

CREATE VIEW IF NOT EXISTS _indirect_relation
AS
SELECT
    'http://en.wikipedia.org/wiki/'||REPLACE(s_title,' ','_') AS wikipedia_url_source,
    'http://en.wikipedia.org/wiki/'||REPLACE(t_title,' ','_') AS wikipedia_url_target,
    'http://en.wikipedia.org/wiki/'||REPLACE(c_title,' ','_') AS wikipedia_url_connection,
    'INDIRECT' AS  relationship_type
FROM (
SELECT s.title AS s_title, t.title AS t_title, c.title AS c_title
FROM article AS s JOIN link AS l ON l.article_id = s.id
    AND s.is_living_person AND l.article_id <> l.ref_article_id
  JOIN link AS l2 ON l2.article_id = l.ref_article_id
    AND l2.article_id <> l2.ref_article_id
    AND l.article_id <> l2.ref_article_id
  JOIN article AS t ON t.id = l2.ref_article_id AND t.is_living_person
    AND t.id <> s.id
  JOIN article AS c ON c.id = l.ref_article_id AND (NOT( c.is_living_person)  OR c.is_living_person IS NULL )
 /* ORDER BY 1,2 */  );
 
CREATE TABLE IF NOT EXISTS indirect_relation AS SELECT * FROM _indirect_relation WHERE 0=1;

-- DELETE FROM  indirect_relation;
INSERT INTO indirect_relation SELECT * FROM _indirect_relation;
