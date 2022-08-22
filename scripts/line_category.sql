SELECT cfl.commit_time,
       cfl.file_name AS file_name,
       cfl.file_dir AS file_dir,
       line.content AS content
  FROM (
        SELECT rcommit.time AS commit_time,
               dir.name AS file_dir,
               strings.text AS file_name,
               file.parent AS file_parent,
               file.id AS file_id
          FROM FILE
         INNER JOIN rcommit
            ON file.rcommit = rcommit.id
         INNER JOIN dir
            ON file.parent = dir.id
         INNER JOIN strings
            ON file.name = strings.id
       ) AS cfl
 INNER JOIN file_lines
    ON file_lines.file = cfl.file_id
 INNER JOIN LINE
    ON file_lines.line = line.id ;
