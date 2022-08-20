SELECT tmp.name AS author_name,
       rcommit.period AS sample_period,
       sum(tmp.lines) AS lines
  FROM (
        SELECT author.name AS name,
               file_lines.file AS FILE,
               count(author.id) AS lines
          FROM file_lines
         INNER JOIN LINE
            ON file_lines.line = line.id
         INNER JOIN rcommit
            ON line.rcommit = rcommit.id
         INNER JOIN author
            ON rcommit.author == author.id
         GROUP BY name,
                  FILE
         ORDER BY lines DESC
       ) AS tmp
 INNER JOIN FILE
    ON tmp.file = file.id
 INNER JOIN rcommit
    ON file.rcommit = rcommit.id
 GROUP BY author_name,
          sample_period
 ORDER BY author_name ASC,
          sample_period DESC;
