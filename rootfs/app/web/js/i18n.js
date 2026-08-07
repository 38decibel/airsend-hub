// i18n.js — Translation dictionary and language utilities
// Supports: fr (default), en
//
// Exposes on window:
//   window.AirSendI18n.t(key, vars)
//   window.AirSendI18n.setLang(lang)
//   window.AirSendI18n.currentLang   (string, read-only via getter)
//   window.AirSendI18n.applyStaticTranslations()
//   window.AirSendI18n.registerRefreshCallback(fn)

"use strict";

const I18N = {
    fr: {
      "page.title": "AirSend - Ajouter un appareil",
      "nav.home": "Appareils",
      "nav.add": "Ajouter",
      "nav.inbox": "Signaux captés",
      "nav.import": "Importer YAML",
      "nav.backup": "Sauvegarde",
      "nav.memory": "Mémoire boîtier",
      "home.devices": "Appareils",
      "home.loading": "Chargement…",
      "home.addDevice": "+ Ajouter un appareil",
      "home.importYaml": "Importer depuis YAML",
      "home.noDevices": "Aucun appareil pour le moment.",
      "home.edit": "Modifier",
      "home.delete": "Supprimer",
      "home.deleteConfirm": "Supprimer \"{name}\" ? Cette action est irréversible et retirera l'appareil de Home Assistant.",
      "home.deleteError": "Erreur lors de la suppression.",

      "edit.title": "Modifier l'appareil",
      "edit.name": "Nom",
      "edit.travelTimeHelp": "Temps approximatif pour aller complètement ouvert ↔ fermé. Utilisé pour estimer quand le volet a fini sa course (pas de retour de position réel).",
      "edit.nameEmptyError": "Le nom ne peut pas être vide.",
      "edit.updateError": "Erreur lors de la mise à jour.",

      "common.save": "Enregistrer",
      "common.cancel": "Annuler",
      "common.back": "Retour",
      "common.backCancel": "&larr; Annuler",
      "common.continue": "Continuer",
      "common.invert": "Inverser le sens (câblage à l'envers)",
      "common.travelTime": "Durée de course estimée (secondes)",
      "common.namePlaceholder": "ex: Volet salon terrasse",

      "wizard.branch.title": "Comment souhaitez-vous ajouter cet appareil ?",
      "wizard.branch.aTitle": "J'ai la télécommande",
      "wizard.branch.aSubtitle": "On écoute la trame RF réelle",
      "wizard.branch.bTitle": "Je n'ai pas la télécommande",
      "wizard.branch.bSubtitle": "Saisie manuelle de l'identifiant",

      "wizard.catalog.title": "Marque",
      "wizard.catalog.searchLabel": "Chercher une marque",
      "wizard.catalog.searchPlaceholder": "ex: Somfy, Profalux…",
      "wizard.catalog.skipBrand": "Passer cette étape (recherche générique 433MHz)",
      "wizard.catalog.skipBrandHelp": "À utiliser si vous ne connaissez ni la marque ni le protocole : l'écoute captera toute trame 433MHz, sans filtrage. Moins précis, en dernier recours.",
      "wizard.catalog.multiProtocol": "Plusieurs protocoles disponibles pour cette marque :",
      "wizard.catalog.rollingCodeBranchA": "⚠️ Développement en cours : la synchronisation des protocoles à code tournant n'est pas encore fonctionnelle. L'inclusion de cet appareil sera probablement incomplète (commandes qui échouent, resynchronisation manuelle nécessaire).",
      "wizard.catalog.rollingCodeBranchB": "⚠️ Développement en cours : la synchronisation des protocoles à code tournant n'est pas encore fonctionnelle. Sans télécommande, l'ajout de cet appareil échouera probablement ou restera incomplet (voir l'avertissement à la confirmation).",

      "wizard.listen.title": "Écoute radio",
      "wizard.listen.instructions": "Sur votre télécommande d'origine, appuyez sur le bouton à copier pendant quelques secondes, dès que vous lancez l'écoute ci-dessous. Répétez l'appui 2 ou 3 fois si rien n'apparaît.",
      "wizard.listen.proximityTip": "💡 Idéalement, placez-vous à environ 1 mètre du boîtier AirSend pendant l'appui, pour optimiser la qualité du signal reçu.",
      "wizard.listen.play": "▶ Écouter (20s)",
      "wizard.listen.retry": "▶ Réessayer (20s)",
      "wizard.listen.startError": "Erreur: {detail}",
      "wizard.listen.startErrorDefault": "impossible de démarrer l'écoute",
      "wizard.listen.inProgress": "Écoute en cours… ({s}s restantes)",
      "wizard.listen.error": "Erreur : {detail}",
      "wizard.listen.done": "Écoute terminée.",
      "wizard.listen.channelFallback": "canal {id}",
      "wizard.listen.useThis": "Utiliser celui-ci",
      "wizard.listen.brandSuggestion": "protocole de la marque",

      "wizard.manual.uidCheckboxLabel": "Saisir un identifiant unique connu",
      "wizard.manual.sourcePlaceholder": "ex: 24679",
      "wizard.manual.sourceHelp": "Cette valeur provient d'un export existant ou d'une capture RF antérieure.",
      "wizard.manual.kindLabel": "Type de télécommande",
      "wizard.manual.kindPlaceholder": "-- Choisir --",
      "wizard.manual.saveButton": "💾 Enregistrer",

      "wizard.kind.title": "Type de matériel",
      "wizard.kind.travelTimeHelp": "Temps approximatif pour aller complètement ouvert ↔ fermé. Modifiable plus tard.",
      "wizard.kind.nameLabel": "Nom de l'appareil",
      "wizard.kind.confirm": "Ajouter l'appareil",
      "wizard.kind.creationError": "Erreur lors de la création de l'appareil.",
      "wizard.kind.tryAnyway": "Continuer quand même",

      "wizard.done.success": "✓ Appareil ajouté avec succès.",

      "wizard.registration.title": "Procédure d'appairage",
      "wizard.registration.info": "Cette procédure est parfois appelée «\u00a0appairage\u00a0», «\u00a0programmation\u00a0» ou «\u00a0mémorisation\u00a0».",
      "wizard.registration.processType": "Type de procédure",
      "wizard.registration.installCode": "Code d'installation",
      "wizard.registration.restart": "Recommencer",
      "wizard.registration.finish": "Terminer",
      "wizard.registration.sending": "Envoi des commandes radio…",
      "wizard.registration.error": "Erreur lors de l'envoi de la commande RF.",
      "wizard.registration.done": "L'enregistrement est terminé.",
      "wizard.registration.doneWait": "L'enregistrement est terminé, veuillez patienter {seconds} secondes avant de tester.",
      "wizard.registration.seeManual": "Veuillez consulter la notice de votre automatisme (section : Ajouter une télécommande supplémentaire) afin d'enregistrer la télécommande ci-dessous.",
      "wizard.registration.pending": "Procédure en cours de documentation — consultez la notice de votre automatisme.",
      "wizard.registration.cmdDown": "Descendre",
      "wizard.registration.cmdStop": "Stop",
      "wizard.registration.cmdUp": "Monter",
      "wizard.registration.pleaseWait": "Veuillez patienter {seconds} secondes…",
      "wizard.registration.proximityTip": "💡 Rapprochez-vous de votre automatisme pour optimiser la portée RF.",
      "wizard.registration.subtype.remote": "A distance",
      "wizard.registration.subtype.automation": "Depuis l'automatisme",
      "wizard.registration.subtype.standard": "Standard",
      "wizard.registration.subtype.beninca": "Benincà",
      "wizard.registration.subtype.clarus": "Clarus",
      "wizard.registration.subtype.situo": "Situo / Smoove",
      "wizard.registration.subtype.keygo": "Keygo",
      "wizard.registration.subtype.velux3ur": "Velux 3UR B01",
      "wizard.registration.subtype.veluxkli": "Velux KLI",
      "wizard.registration.subtype.florStandard": "Standard",
      "wizard.registration.subtype.florShort": "Short",
      "wizard.registration.subtype.florAlternative": "Alternative",
      "wizard.registration.subtype.florCode": "Code",
      "wizard.registration.actionButton": "ACTION",
      "wizard.registration.actionInvButton": "ACTION (inversion)",
      "wizard.registration.pairButton": "Appairer",
      "wizard.registration.unpairButton": "Désappairer",
      "wizard.registration.startButton": "Commencer",
      "wizard.registration.progButton": "PROG",

      "kind.1_bouton": "1 bouton",
      "kind.on_off": "On / Off",
      "kind.volet_roulant": "Volet roulant",
      "kind.niveau": "Niveau (position)",

      "import.title": "Importer depuis le YAML de l'ancienne intégration",
      "import.instructions": "Colle le contenu de ton fichier (ex. <code>airsend.yaml</code>), ou choisis un fichier. Rien n'est modifié tant que tu n'as pas confirmé à l'étape suivante.",
      "import.useThisFile": "Utiliser ce fichier",
      "import.fileInputAria": "Fichier YAML à importer",
      "import.textareaAria": "Contenu YAML",
      "import.textareaPlaceholder": "devices:\n  Volet Celyan:\n    type: 4098\n    channel:\n      id: 25455\n      source: 233575",
      "import.analyze": "Analyser",
      "import.detected": "Fichier détecté : {path}",
      "import.previewTitle": "Vérifier avant import",
      "import.col.name": "Nom",
      "import.col.protocol": "Protocole",
      "import.col.status": "Statut",
      "import.col.domain": "Domain",
      "import.col.kind": "Kind",
      "import.col.conflict": "Si conflit",
      "import.commit": "Importer la sélection",
      "import.parseError": "Erreur lors de l'analyse du YAML.",
      "import.commitError": "Erreur lors de l'import.",
      "import.domainAriaLabel": "Domaine pour {name}",
      "import.kindAriaLabel": "Type de materiel pour {name}",
      "import.conflictAriaLabel": "Action en cas de conflit pour {name}",
      "import.conflictKeepExisting": "garder existant",
      "import.conflictOverwrite": "écraser",
      "import.kindTranslatedNote": "kind traduit depuis l'ancien format",
      "import.checkboxAriaLabel": "Importer {name}",
      "import.summary.newSingular": "{n} nouveau",
      "import.summary.newPlural": "{n} nouveaux",
      "import.summary.conflictSingular": "{n} conflit",
      "import.summary.conflictPlural": "{n} conflits",
      "import.summary.unknownSingular": "{n} protocole inconnu",
      "import.summary.unknownPlural": "{n} protocoles inconnus",
      "import.modify": "Modifier",
      "import.collapse": "Réduire",
      "import.toggleAriaLabel": "Afficher/masquer les champs pour {name}",
      "import.unknownProtocolNote": "Protocole non reconnu : cet appareil ne peut pas encore être importé automatiquement.",
      "import.resultSummary": "{added} ajoutés, {overwritten} écrasés, {skipped} ignorés.",
      "import.resultErrors": " Erreurs: {errors}",

      "home.backup": "Sauvegarde / restauration",
      "home.inbox": "📡 Signaux captés",
      "home.memory": "🧠 Mémoire boîtier",
      "memory.title": "Mémoire boîtier",
      "memory.instructions": "Liste des appareils enregistrés dans la mémoire interne du boîtier AirSend. Les appareils liés sont déjà gérés par l'addon. Les orphelins sont présents en mémoire mais absents de la configuration.",
      "memory.linked": "Lié",
      "memory.orphan": "Orphelin",
      "memory.loadError": "Erreur lors du chargement de la mémoire.",
      "memory.addTitle": "Ajouter cet appareil",
      "memory.add": "Ajouter",
      "memory.counter": "Compteur : {n}",
      "memory.creationError": "Erreur lors de la création de l'appareil.",
      "memory.usage": "Mémoire utilisée : {n} / {max} appareils",

      "inbox.detailChannelId":  "Channel ID :",
      "inbox.detailSource":     "Source :",
      "inbox.detailFirstSeen":  "1re détection :",
      "inbox.detailLastNotes":  "Dernières notes :",
      "inbox.bindChannelLabel": "Protocole d'écoute permanente",
      "inbox.bindChannelAll": "Tous les protocoles (défaut)",
      "inbox.bindChannelHelp": "Le changement relance immédiatement l'écoute sur ce protocole.",
      "inbox.title": "Signaux captés",
      "inbox.instructions": "Toute trame RF reçue par le boîtier et ne correspondant à aucun appareil déjà ajouté apparaît ici, que le protocole soit reconnu ou non — que l'assistant d'ajout soit ouvert ou non.",
      "inbox.captureUnknownLabel": "Capturer aussi les protocoles non reconnus (mode promiscuous)",
      "inbox.captureUnknownWarning": "⚠️ Peut capter des signaux qui ne sont pas les vôtres (voisins, véhicules qui passent…) et remplir la liste rapidement. Utilisez \"Oublier\" pour masquer durablement une source indésirable.",
      "inbox.empty": "Aucun signal en attente pour le moment.",
      "inbox.loading": "Chargement…",
      "inbox.decoded": "Protocole reconnu",
      "inbox.undecoded": "Protocole non reconnu",
      "inbox.seenCount": "vu {n} fois",
      "inbox.lastSeen": "dernière réception : {when}",
      "inbox.band433": "433MHz",
      "inbox.band868": "868MHz",
      "inbox.bandUnknown": "bande inconnue",
      "inbox.include": "Inclure",
      "inbox.forget": "Oublier",
      "inbox.forgetConfirm": "Oublier définitivement ce signal (channel {channelId}/{channelSource}) ? Il ne réapparaîtra plus dans cette liste, même s'il est reçu à nouveau.",
      "inbox.includeTitle": "Ajouter cet appareil",
      "inbox.settingsError": "Erreur lors de la mise à jour du réglage.",
      "inbox.loadError": "Erreur lors du chargement des signaux.",

      "category.none": "— aucune —",
      "category.other": "Autre capteur / appareil",
      "category.temp_humidity": "Température & humidité",
      "category.weather_station": "Station météo",
      "category.tpms": "Pression pneus (TPMS)",
      "category.energy_water_meter": "Compteur énergie / eau",
      "category.smoke_security_alarm": "Fumée / alarme sécurité",
      "category.gate_garage_remote": "Télécommande portail / garage",
      "category.automotive_keyfob": "Clé automobile",
      "category.remote_keyfob": "Télécommande / badge",
      "category.home_automation_blinds": "Domotique / volets",
      "category.ceiling_fan": "Ventilateur de plafond",
      "category.kitchen_thermometer": "Thermomètre cuisine / barbecue",
      "category.doorbell": "Sonnette",
      "category.rolling_code": "Système à code tournant",
      "category.restaurant_pager": "Pager restaurant",

      "wizard.kind.categoryLabel": "Catégorie (icône, facultatif)",

      "backup.exportTitle": "Exporter",
      "backup.exportInstructions": "Télécharge la configuration actuelle des appareils. Conserve ce fichier avant une désinstallation : le réimporter ensuite réattache les mêmes appareils dans Home Assistant, sans doublons.",
      "backup.exportButton": "⬇ Télécharger la sauvegarde",
      "backup.importTitle": "Restaurer",
      "backup.importInstructions": "Choisis un fichier de sauvegarde précédemment exporté. Rien n'est modifié tant que tu n'as pas confirmé à l'étape suivante.",
      "backup.fileInputAria": "Fichier de sauvegarde à importer",
      "backup.analyze": "Analyser",
      "backup.previewTitle": "Vérifier avant restauration",
      "backup.commit": "Restaurer la sélection",
      "backup.parseError": "Erreur lors de l'analyse du fichier de sauvegarde.",
      "backup.commitError": "Erreur lors de la restauration.",
      "backup.resultSummary": "{imported} restaurés, {overwritten} écrasés, {skipped} ignorés.",
      "backup.resultErrors": " Erreurs: {errors}",
      "backup.checkboxAriaLabel": "Restaurer {name}",
      "backup.actionAriaLabel": "Action pour {name}",
      "backup.boxSelectAriaLabel": "Box cible pour {name}",
      "backup.boxSelectPlaceholder": "-- choisir une box --",
      "backup.status.new": "nouveau",
      "backup.status.identical": "déjà à jour",
      "backup.status.conflict": "conflit",
      "backup.status.unknown_box": "box inconnue",
      "backup.status.invalid_kind": "type inconnu",
      "backup.action.skip": "ignorer",
      "backup.action.import": "importer",
      "backup.action.overwrite": "écraser l'existant",
      "backup.summary.newSingular": "{n} nouveau",
      "backup.summary.newPlural": "{n} nouveaux",
      "backup.summary.conflictSingular": "{n} conflit",
      "backup.summary.conflictPlural": "{n} conflits",
      "backup.summary.identicalSingular": "{n} déjà à jour",
      "backup.summary.identicalPlural": "{n} déjà à jour",
      "backup.summary.unknown_boxSingular": "{n} box inconnue",
      "backup.summary.unknown_boxPlural": "{n} box inconnues",
      "backup.summary.invalid_kindSingular": "{n} type inconnu",
      "backup.summary.invalid_kindPlural": "{n} types inconnus",
    },
    en: {
      "page.title": "AirSend - Add a device",
      "nav.home": "Devices",
      "nav.add": "Add",
      "nav.inbox": "Captured signals",
      "nav.import": "Import YAML",
      "nav.backup": "Backup",
      "nav.memory": "Box memory",
      "home.devices": "Devices",
      "home.loading": "Loading…",
      "home.addDevice": "+ Add a device",
      "home.importYaml": "Import from YAML",
      "home.noDevices": "No devices yet.",
      "home.edit": "Edit",
      "home.delete": "Delete",
      "home.deleteConfirm": "Delete \"{name}\"? This action is irreversible and will remove the device from Home Assistant.",
      "home.deleteError": "Error while deleting.",

      "edit.title": "Edit device",
      "edit.name": "Name",
      "edit.travelTimeHelp": "Approximate time to travel fully open ↔ closed. Used to estimate when the cover has finished moving (no real position feedback).",
      "edit.nameEmptyError": "Name cannot be empty.",
      "edit.updateError": "Error while updating.",

      "common.save": "Save",
      "common.cancel": "Cancel",
      "common.back": "Back",
      "common.backCancel": "&larr; Cancel",
      "common.continue": "Continue",
      "common.invert": "Invert direction (wired backwards)",
      "common.travelTime": "Estimated travel time (seconds)",
      "common.namePlaceholder": "e.g. Living room shutter",

      "wizard.branch.title": "How would you like to add this device?",
      "wizard.branch.aTitle": "I have the remote",
      "wizard.branch.aSubtitle": "We'll listen to the actual RF signal",
      "wizard.branch.bTitle": "I don't have the remote",
      "wizard.branch.bSubtitle": "Manual entry of the identifier",

      "wizard.catalog.title": "Brand",
      "wizard.catalog.searchLabel": "Search for a brand",
      "wizard.catalog.searchPlaceholder": "e.g. Somfy, Profalux…",
      "wizard.catalog.skipBrand": "Skip this step (generic 433MHz search)",
      "wizard.catalog.skipBrandHelp": "Use this if you know neither the brand nor the protocol: listening will capture any 433MHz signal, unfiltered. Less precise, last resort.",
      "wizard.catalog.multiProtocol": "Several protocols are available for this brand:",
      "wizard.catalog.rollingCodeBranchA": "⚠️ Under active development: rolling-code counter synchronization does not work yet. Including this device will likely be incomplete (commands may fail, manual resync may be required).",
      "wizard.catalog.rollingCodeBranchB": "⚠️ Under active development: rolling-code counter synchronization does not work yet. Without the remote, adding this device will likely fail or remain incomplete (see the warning at confirmation).",

      "wizard.listen.title": "RF listening",
      "wizard.listen.instructions": "On your original remote, press the button to copy for a few seconds as soon as you start listening below. Repeat 2 or 3 times if nothing appears.",
      "wizard.listen.proximityTip": "💡 Ideally, stand about 1 meter from the AirSend box while pressing, to get the best signal quality.",
      "wizard.listen.play": "▶ Listen (20s)",
      "wizard.listen.retry": "▶ Retry (20s)",
      "wizard.listen.startError": "Error: {detail}",
      "wizard.listen.startErrorDefault": "unable to start listening",
      "wizard.listen.inProgress": "Listening… ({s}s remaining)",
      "wizard.listen.error": "Error: {detail}",
      "wizard.listen.done": "Listening finished.",
      "wizard.listen.channelFallback": "channel {id}",
      "wizard.listen.useThis": "Use this one",
      "wizard.listen.brandSuggestion": "brand protocol",

      "wizard.manual.uidCheckboxLabel": "Enter a known unique identifier",
      "wizard.manual.sourcePlaceholder": "e.g. 24679",
      "wizard.manual.sourceHelp": "This value comes from an existing export or a previous RF capture.",
      "wizard.manual.kindLabel": "Remote type",
      "wizard.manual.kindPlaceholder": "-- Choose --",
      "wizard.manual.saveButton": "💾 Save",

      "wizard.kind.title": "Device type",
      "wizard.kind.travelTimeHelp": "Approximate time to travel fully open ↔ closed. Can be changed later.",
      "wizard.kind.nameLabel": "Device name",
      "wizard.kind.confirm": "Add device",
      "wizard.kind.creationError": "Error while creating the device.",
      "wizard.kind.tryAnyway": "Continue anyway",

      "wizard.done.success": "✓ Device added successfully.",

      "wizard.registration.title": "Pairing procedure",
      "wizard.registration.info": "This process is sometimes called \"pairing\", \"programming\" or \"memorizing\".",
      "wizard.registration.processType": "Process type",
      "wizard.registration.installCode": "Installation code",
      "wizard.registration.restart": "Restart",
      "wizard.registration.finish": "Finish",
      "wizard.registration.sending": "Sending radio commands…",
      "wizard.registration.error": "Error sending RF command.",
      "wizard.registration.done": "Registration is complete.",
      "wizard.registration.doneWait": "Registration is complete, please wait {seconds} seconds before testing.",
      "wizard.registration.seeManual": "Please consult your automation manual (section: Adding an additional remote control) in order to register the remote control below.",
      "wizard.registration.pending": "Procedure pending documentation — please consult your automation manual.",
      "wizard.registration.cmdDown": "Down",
      "wizard.registration.cmdStop": "Stop",
      "wizard.registration.cmdUp": "Up",
      "wizard.registration.pleaseWait": "Please wait {seconds} seconds…",
      "wizard.registration.proximityTip": "💡 Move closer to your automation to optimise RF range.",
      "wizard.registration.subtype.remote": "Remotely",
      "wizard.registration.subtype.automation": "From the automation",
      "wizard.registration.subtype.standard": "Standard",
      "wizard.registration.subtype.beninca": "Benincà",
      "wizard.registration.subtype.clarus": "Clarus",
      "wizard.registration.subtype.situo": "Situo / Smoove",
      "wizard.registration.subtype.keygo": "Keygo",
      "wizard.registration.subtype.velux3ur": "Velux 3UR B01",
      "wizard.registration.subtype.veluxkli": "Velux KLI",
      "wizard.registration.subtype.florStandard": "Standard",
      "wizard.registration.subtype.florShort": "Short",
      "wizard.registration.subtype.florAlternative": "Alternative",
      "wizard.registration.subtype.florCode": "Code",
      "wizard.registration.actionButton": "ACTION",
      "wizard.registration.actionInvButton": "ACTION (inversion)",
      "wizard.registration.pairButton": "Pair",
      "wizard.registration.unpairButton": "Unpair",
      "wizard.registration.startButton": "Start",
      "wizard.registration.progButton": "PROG",

      "kind.1_bouton": "Single button",
      "kind.on_off": "On / Off",
      "kind.volet_roulant": "Roller shutter",
      "kind.niveau": "Level (position)",

      "import.title": "Import from the old integration's YAML",
      "import.instructions": "Paste the contents of your file (e.g. <code>airsend.yaml</code>), or choose a file. Nothing is changed until you confirm on the next step.",
      "import.useThisFile": "Use this file",
      "import.fileInputAria": "YAML file to import",
      "import.textareaAria": "YAML content",
      "import.textareaPlaceholder": "devices:\n  Living room shutter:\n    type: 4098\n    channel:\n      id: 25455\n      source: 233575",
      "import.analyze": "Analyze",
      "import.detected": "File detected: {path}",
      "import.previewTitle": "Review before import",
      "import.col.name": "Name",
      "import.col.protocol": "Protocol",
      "import.col.status": "Status",
      "import.col.domain": "Domain",
      "import.col.kind": "Kind",
      "import.col.conflict": "If conflict",
      "import.commit": "Import selection",
      "import.parseError": "Error while parsing the YAML.",
      "import.commitError": "Error while importing.",
      "import.domainAriaLabel": "Domain for {name}",
      "import.kindAriaLabel": "Device type for {name}",
      "import.conflictAriaLabel": "Action on conflict for {name}",
      "import.conflictKeepExisting": "keep existing",
      "import.conflictOverwrite": "overwrite",
      "import.kindTranslatedNote": "kind translated from the old format",
      "import.checkboxAriaLabel": "Import {name}",
      "import.summary.newSingular": "{n} new",
      "import.summary.newPlural": "{n} new",
      "import.summary.conflictSingular": "{n} conflict",
      "import.summary.conflictPlural": "{n} conflicts",
      "import.summary.unknownSingular": "{n} unknown protocol",
      "import.summary.unknownPlural": "{n} unknown protocols",
      "import.modify": "Modify",
      "import.collapse": "Collapse",
      "import.toggleAriaLabel": "Show or hide fields for {name}",
      "import.unknownProtocolNote": "Unrecognized protocol — this device can't be imported automatically yet.",
      "import.resultSummary": "{added} added, {overwritten} overwritten, {skipped} skipped.",
      "import.resultErrors": " Errors: {errors}",

      "home.backup": "Backup / restore",
      "home.inbox": "📡 Captured signals",
      "home.memory": "🧠 Box memory",
      "memory.title": "Box memory",
      "memory.instructions": "List of devices registered in the AirSend box internal memory. Linked devices are already managed by the addon. Orphans are present in memory but missing from the configuration.",
      "memory.linked": "Linked",
      "memory.orphan": "Orphan",
      "memory.loadError": "Error loading memory.",
      "memory.addTitle": "Add this device",
      "memory.add": "Add",
      "memory.counter": "Counter: {n}",
      "memory.creationError": "Error while creating device.",
      "memory.usage": "Memory used: {n} / {max} devices",

      "inbox.detailChannelId":  "Channel ID:",
      "inbox.detailSource":     "Source:",
      "inbox.detailFirstSeen":  "First seen:",
      "inbox.detailLastNotes":  "Last notes:",
      "inbox.bindChannelLabel": "Permanent listen protocol",
      "inbox.bindChannelAll": "All protocols (default)",
      "inbox.bindChannelHelp": "Changing this immediately restarts the listen session on the selected protocol.",
      "inbox.title": "Captured signals",
      "inbox.instructions": "Every RF frame received by the box that doesn't match an already-added device shows up here, whether the protocol is recognized or not — whether the add-device wizard is open or not.",
      "inbox.captureUnknownLabel": "Also capture unrecognized protocols (promiscuous mode)",
      "inbox.captureUnknownWarning": "⚠️ May pick up signals that aren't yours (neighbours, passing vehicles…) and fill up the list quickly. Use \"Forget\" to permanently hide an unwanted source.",
      "inbox.empty": "No pending signal at the moment.",
      "inbox.loading": "Loading…",
      "inbox.decoded": "Recognized protocol",
      "inbox.undecoded": "Unrecognized protocol",
      "inbox.seenCount": "seen {n} times",
      "inbox.lastSeen": "last received: {when}",
      "inbox.band433": "433MHz",
      "inbox.band868": "868MHz",
      "inbox.bandUnknown": "unknown band",
      "inbox.include": "Include",
      "inbox.forget": "Forget",
      "inbox.forgetConfirm": "Permanently forget this signal (channel {channelId}/{channelSource})? It won't reappear in this list, even if received again.",
      "inbox.includeTitle": "Add this device",
      "inbox.settingsError": "Error while updating the setting.",
      "inbox.loadError": "Error while loading captured signals.",

      "category.none": "— none —",
      "category.other": "Other sensor / device",
      "category.temp_humidity": "Temperature & humidity",
      "category.weather_station": "Weather station",
      "category.tpms": "Tire pressure (TPMS)",
      "category.energy_water_meter": "Energy / water meter",
      "category.smoke_security_alarm": "Smoke / security alarm",
      "category.gate_garage_remote": "Gate / garage remote",
      "category.automotive_keyfob": "Automotive key fob",
      "category.remote_keyfob": "Remote / keyfob",
      "category.home_automation_blinds": "Home automation / blinds",
      "category.ceiling_fan": "Ceiling fan",
      "category.kitchen_thermometer": "Kitchen / BBQ thermometer",
      "category.doorbell": "Doorbell",
      "category.rolling_code": "Rolling code system",
      "category.restaurant_pager": "Restaurant pager",

      "wizard.kind.categoryLabel": "Category (icon, optional)",

      "backup.exportTitle": "Export",
      "backup.exportInstructions": "Download the current device configuration. Keep this file before uninstalling: re-importing it afterwards re-attaches the same devices in Home Assistant, without duplicates.",
      "backup.exportButton": "⬇ Download backup",
      "backup.importTitle": "Restore",
      "backup.importInstructions": "Choose a previously exported backup file. Nothing is changed until you confirm on the next step.",
      "backup.fileInputAria": "Backup file to import",
      "backup.analyze": "Analyze",
      "backup.previewTitle": "Review before restoring",
      "backup.commit": "Restore selection",
      "backup.parseError": "Error while parsing the backup file.",
      "backup.commitError": "Error while restoring.",
      "backup.resultSummary": "{imported} restored, {overwritten} overwritten, {skipped} skipped.",
      "backup.resultErrors": " Errors: {errors}",
      "backup.checkboxAriaLabel": "Restore {name}",
      "backup.actionAriaLabel": "Action for {name}",
      "backup.boxSelectAriaLabel": "Target box for {name}",
      "backup.boxSelectPlaceholder": "-- choose a box --",
      "backup.status.new": "new",
      "backup.status.identical": "up to date",
      "backup.status.conflict": "conflict",
      "backup.status.unknown_box": "unknown box",
      "backup.status.invalid_kind": "unknown type",
      "backup.action.skip": "skip",
      "backup.action.import": "import",
      "backup.action.overwrite": "overwrite existing",
      "backup.summary.newSingular": "{n} new",
      "backup.summary.newPlural": "{n} new",
      "backup.summary.conflictSingular": "{n} conflict",
      "backup.summary.conflictPlural": "{n} conflicts",
      "backup.summary.identicalSingular": "{n} up to date",
      "backup.summary.identicalPlural": "{n} up to date",
      "backup.summary.unknown_boxSingular": "{n} unknown box",
      "backup.summary.unknown_boxPlural": "{n} unknown boxes",
      "backup.summary.invalid_kindSingular": "{n} unknown type",
      "backup.summary.invalid_kindPlural": "{n} unknown types",
    },
  };

const SUPPORTED_LANGS = new Set(["fr", "en"]);
const LANG_STORAGE_KEY = "airsend_lang";

function detectDefaultLang() {
  const nav = (navigator.language || "fr").toLowerCase();
  return nav.includes("en") ? "en" : "fr";
}

function loadStoredLang() {
  try {
    const stored = window.localStorage.getItem(LANG_STORAGE_KEY);
    return SUPPORTED_LANGS.includes(stored) ? stored : null;
  } catch {
    return null;
  }
}

let _currentLang = loadStoredLang() || detectDefaultLang();
let _onRefresh = null;

function t(key, vars) {
  const dict = I18N[_currentLang] || I18N.fr;
  let text = Object.hasOwn(dict, key)
    ? dict[key]
    : (I18N.fr[key] || key);
  if (vars) {
    Object.keys(vars).forEach(function (k) {
      text = text.replace("{" + k + "}", vars[k]);
    });
  }
  return text;
}

function applyStaticTranslations() {
  document.documentElement.lang = _currentLang;
  document.querySelectorAll("[data-i18n]").forEach(function (el) {
    el.innerHTML = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
    el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
    el.setAttribute("aria-label", t(el.dataset.i18nAria));
  });
  document.title = t("page.title");
  document.querySelectorAll(".lang-switch button").forEach(function (btn) {
    btn.classList.toggle("active", btn.dataset.lang === _currentLang);
  });
}

// onRefresh is injected by the main script to avoid coupling i18n
// to screen modules that do not exist yet in this file.
function registerRefreshCallback(fn) {
  _onRefresh = fn;
}

function setLang(lang) {
  if (!SUPPORTED_LANGS.includes(lang) || lang === _currentLang) {
    applyStaticTranslations();
    return;
  }
  _currentLang = lang;
  try { window.localStorage.setItem(LANG_STORAGE_KEY, lang); } catch (e) { /* ignore storage errors */ }
  applyStaticTranslations();
  if (_onRefresh) { _onRefresh(); }
}

// Expose public API on window for use by the inline script
// until all screens are extracted to ES modules (PR5).
window.AirSendI18n = {
  get currentLang() { return _currentLang; },
  t,
  setLang,
  applyStaticTranslations,
  registerRefreshCallback,
};
