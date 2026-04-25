# client

### Ветки

Для корректной интеграции с JIRA, все branches должны быть именованы согласно следующему формату:

`[proj]-[task]-[some-description]`

Примеры: `fep-100-do-something`, `arc-123-do-sothing-else`

### Коммиты

В целях поддержания "чистой" и информативной истории коммитов, все коммиты должны conventional commit rules (Angular style).

Подробнее: [Conventional commits specification](https://www.conventionalcommits.org/en/v1.0.0/#specification)

> Для создания коммитов, используя специальный CLI, выполните команду `yarn commit`.

Формат коммитов: `$type($scope)?: $message`

Также достустим расширенный формат:
```
$type($scope)?: $message
<blank line>
$Commitbody
<blank line>
$Commitfooter
```

Примеры:

`feat(webpack-config): Add some loader`

`chore: Fix storybook config`

```
refactor!: Use lerna for releases

Description of work

BREAKING CHANGE: Node v10 is not supported anymore
```

### Релизы

Публикация пакетов происходит автоматически посредством Continues Integration

Версия определяется согласно [Conventional commits specification](https://www.conventionalcommits.org/en/v1.0.0/#specification)

Например, следующие $type коммитов:
- `fix` - поднимет PATCH версию пакетов
- `feat` - поднимет MINOR версию
- Коммиты, содержащие $footer `BREAKING CHANGE:`, или `!` сразу после $type/$scope (например, `feat!: message`) поднимет MAJOR версию

**Changelog также генерируется автоматически исходя из истории коммитов**.