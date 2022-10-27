SELECT avg((
      CASE
        WHEN NOT (pull.merged_at IS NULL) THEN pull.merged_at
        WHEN NOT (pull.closed_at IS NULL) THEN pull.closed_at
        ELSE strftime('%s', 'now')
      END
  ) - pull.created_at) AS "average"
  FROM pull
  ;
