-- Dernière évaluation de chaque annonce.
SELECT * EXCEPT (rn)
FROM (
  SELECT e.*, ROW_NUMBER() OVER (PARTITION BY source, listing_id ORDER BY evaluated_at DESC) AS rn
  FROM `${project}.${dataset}.evaluations` AS e
)
WHERE rn = 1
