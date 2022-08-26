SELECT cfl.commit_time,
       fv.path AS file_name,
       fv.dir AS file_dir,
       line.content AS content
  FROM (
        SELECT rcommit.time AS commit_time,
               file.id AS file_id
          FROM FILE
         INNER JOIN rcommit
            ON file.rcommit = rcommit.id
       ) AS cfl
 INNER JOIN file_lines
    ON file_lines.file = cfl.file_id
 INNER JOIN LINE
    ON file_lines.line = line.id
 INNER JOIN file_version_with_path_dir fv
    ON fv.id = cfl.file_id;
