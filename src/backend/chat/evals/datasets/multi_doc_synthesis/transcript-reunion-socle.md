Transcription automatique — réunion « Ouverture du Socle IA au ministère de l'Agriculture »
Date : 12 mars 2026, 10 h 00 – 11 h 05, visioconférence
Participants : Nadia Ferrière (cheffe de projet Socle), Bruno Castel (DSI adjoint, ministère de l'Agriculture), Léa Morvan (juriste, direction des affaires juridiques), Olivier Mercadier (RSSI ministériel), Camille Joubert (référente IA du ministère)

[00:00] Nadia Ferrière : Bonjour à tous. L'objet de la réunion, c'est de voir si on peut ouvrir le Socle aux agents de l'Agriculture d'ici le 1er juin. On a trois sujets : le volume d'usage attendu, la question des données, et le financement. Bruno, tu veux commencer par vos besoins ?

[01:12] Bruno Castel : Oui. Côté Agriculture, on a identifié deux cas d'usage prioritaires. Le premier, c'est l'aide à la rédaction des réponses aux courriers d'exploitants agricoles, à peu près 40 000 courriers par an dans les directions départementales. Le second, c'est la synthèse des rapports d'inspection sanitaire, qui sont longs et très techniques. On estime entre 1 500 et 2 000 utilisateurs la première année.

[02:40] Nadia Ferrière : D'accord. À ce volume-là, l'inférence ne pose pas de problème, on absorbe déjà beaucoup plus. Le vrai sujet, c'est plutôt les données. Olivier, tu avais des réserves ?

[03:05] Olivier Mercadier : Oui, et elles sont sérieuses. Les rapports d'inspection sanitaire contiennent parfois des informations nominatives sur les exploitants, et certains sont classés diffusion limitée quand il y a une enquête en cours. Tant qu'on n'a pas une analyse de risque signée, je ne peux pas valider l'envoi de ces documents vers le Socle. Les courriers, en revanche, ça me pose moins de problème.

[04:30] Nadia Ferrière : Le Socle a le label Nuage de confiance, est-ce que ça ne lève pas l'essentiel de tes réserves ?

[04:41] Olivier Mercadier : Ça règle la question de l'hébergement, pas celle de la diffusion limitée. Pour les documents DL, il faut une homologation spécifique du traitement, et elle n'existe pas aujourd'hui. Je ne dis pas non, je dis pas avant l'homologation.

[05:50] Léa Morvan : Je complète côté juridique. Pour les données nominatives des exploitants, il faudra mettre à jour le registre des traitements et probablement faire une analyse d'impact. Ce n'est pas bloquant en soi, mais ça prend au minimum deux mois si on veut un avis du délégué à la protection des données.

[07:15] Bruno Castel : Deux mois, plus l'homologation, on ne tient pas le 1er juin pour les rapports d'inspection. C'est clair.

[07:32] Camille Joubert : Est-ce qu'on ne pourrait pas démarrer par les courriers seulement ? Ils ne contiennent pas de DL, et pour les données nominatives on peut demander aux agents de pseudonymiser avant envoi.

[08:10] Olivier Mercadier : La pseudonymisation manuelle, je n'y crois pas trop. Les agents vont oublier. Si on part sur les courriers, je préfère un filtrage automatique des noms et numéros SIRET avant envoi.

[09:02] Nadia Ferrière : On a une brique d'anonymisation en test côté Socle, mais elle n'est pas en production. Je ne peux pas m'engager sur une date avant la fin du mois.

[10:20] Bruno Castel : Le deuxième point, c'est l'argent. Notre DSI n'a pas budgété de contribution au calcul mutualisé pour 2026. On a compris que les ministères co-financeurs passent devant les autres pour les nouveaux cas d'usage. C'est vrai ?

[11:05] Nadia Ferrière : En pratique, oui. Les priorités de la feuille de route sont arbitrées au comité partenarial, et les co-financeurs y ont plus de poids. Mais l'accès de base au Socle n'est pas conditionné au financement. Ce qui est conditionné, ce sont les développements spécifiques, par exemple un connecteur vers votre outil de gestion des courriers.

[12:30] Bruno Castel : Justement, sans connecteur, les agents devront copier-coller les courriers dans l'interface. Ça marche pour un pilote, pas pour 2 000 personnes.

[13:10] Camille Joubert : Pour le pilote, on peut se contenter du copier-coller avec une centaine d'agents volontaires dans deux directions départementales. Ça nous donnerait des chiffres de gain de temps pour défendre le budget 2027.

[14:25] Léa Morvan : Si c'est un pilote limité sur les courriers, le registre des traitements suffit, pas besoin d'analyse d'impact complète. Ça, je peux le faire en trois semaines.

[15:40] Olivier Mercadier : Pilote sur les courriers, cent agents, sans rapport d'inspection et sans DL : je peux vivre avec. Mais je veux une consigne écrite qui interdit explicitement d'y mettre des documents d'enquête, et un point de contrôle à un mois.

[16:50] Nadia Ferrière : Ça me va. Pour résumer ce que j'entends, le point de blocage principal, ce sont les rapports d'inspection, à cause de la diffusion limitée et de l'absence d'homologation. Le reste, on peut avancer.

[17:30] Bruno Castel : Oui, mais je ne veux pas que le pilote enterre le cas des rapports. C'est là qu'on a le plus de gains, les inspecteurs passent des journées entières dessus.

[18:15] Olivier Mercadier : Alors il faut lancer le dossier d'homologation maintenant, en parallèle du pilote, et pas après. Sinon on en reparle dans un an.

[19:00] Nadia Ferrière : Qui porte le dossier d'homologation ?

[19:12] Bruno Castel : Normalement la DSI, mais on n'a personne de disponible avant septembre.

[19:40] Camille Joubert : Je peux le porter si Olivier m'accompagne sur la partie sécurité. Je n'ai pas la compétence pour l'analyse de risque seule.

[20:05] Olivier Mercadier : Je n'ai pas le temps de l'écrire, mais je peux relire et valider.

[20:30] Nadia Ferrière : On reste donc avec une question ouverte sur qui rédige l'analyse de risque. Je propose qu'on en reparle en comité de direction du ministère. Prochaine réunion dans trois semaines.

[21:00] Fin de la transcription.
