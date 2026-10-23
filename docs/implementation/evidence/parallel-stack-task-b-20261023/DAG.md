# Reconstructed PR DAG at startup

The base SHA is the API-reported PR base snapshot; resolve current branch refs separately before integrating. Actual merge-base and ancestry were recomputed from real Git objects. All open PRs and recent closed/merged PRs numbered >=100 are included. Full tree SHAs and parents are in raw/github-start.json.

| PR | State | API base branch / SHA | Head branch / SHA | Actual merge-base | API base ancestor? |
| --- | --- | --- | --- | --- | --- |
| #100 | merged | `main` / `5e04f0c523f46f64ad35e34c2140b7019eb25cd1` | `feat/access-a4-local-git-acquisition` / `2ab6a59dd91c46ebbc9a9d14a0078f2b16235b4f` | `c82fe24454926e2213a476f7bdfd7650519b12b6` | False |
| #101 | merged | `main` / `ba5b9aca9c9b0666d95fe5d234ce3dfef7cb18ad` | `feat/access-a5-backup-restore` / `444dcecf38f5db3cccdb4716c7c8c6b584543475` | `2ab6a59dd91c46ebbc9a9d14a0078f2b16235b4f` | False |
| #102 | merged | `main` / `112368a4ce041cd96448d75e1a326b9012d1a410` | `validation/access-a6-integration-review` / `f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60` | `444dcecf38f5db3cccdb4716c7c8c6b584543475` | False |
| #103 | merged | `main` / `0c847a5f90cf2c49ccd3a0b94199b15356d8aee1` | `fix/access-a6-independent-review` / `1134e200eb4ac9ec45bf3fae3be695e2bb786a8d` | `f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60` | False |
| #104 | merged | `main` / `7703f06470be82b6a88d0bcd5995071f87a22331` | `docs/context-relations-selective-exchange-20261018` / `bb54d799d1b749a90fa62de89dbd978ef3bc8055` | `1134e200eb4ac9ec45bf3fae3be695e2bb786a8d` | False |
| #105 | merged | `main` / `83b742fdfd2dd730f03a5556d468ac99c55f91ec` | `docs/adr-0029-replacement-readiness-20261019` / `bb878eda47cf17268dd821c74343bac64d769ea7` | `bb54d799d1b749a90fa62de89dbd978ef3bc8055` | False |
| #106 | merged | `main` / `5bbc6883f5223acad53528d43c40868f922391f6` | `docs/accept-adr-0029-retire-0003-20261019` / `ea3d0dd0bd369f16987d574c5f17529f5399d26b` | `bb878eda47cf17268dd821c74343bac64d769ea7` | False |
| #107 | merged | `main` / `6780088befd33e711230d570bb291edb2ee40cbf` | `impl/adr-0030-i1-context-relations-20261019` / `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | `6780088befd33e711230d570bb291edb2ee40cbf` | True |
| #108 | closed | `impl/adr-0030-i1-context-relations-20261019` / `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | `impl/adr-0030-i3-selective-exchange-20261019` / `5c5b816998f7051703ca400e8cfeab377254c435` | `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | True |
| #109 | closed | `impl/adr-0030-i1-context-relations-20261019` / `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | `impl/adr-0030-i2-provider-intake-20261019` / `9b8a6ad9b761bf23b45eda9f84d639569cee56ef` | `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | True |
| #110 | closed | `impl/adr-0030-i2-provider-intake-20261019` / `9b8a6ad9b761bf23b45eda9f84d639569cee56ef` | `impl/adr-0030-i23-integration-20261019` / `8519056d5b9484eb0cc4dcf9f693285b4e65518a` | `9b8a6ad9b761bf23b45eda9f84d639569cee56ef` | True |
| #111 | closed | `impl/adr-0030-i23-integration-20261019` / `8519056d5b9484eb0cc4dcf9f693285b4e65518a` | `impl/adr-0030-i4-query-search-backup-20261019` / `a54cb218226e3c91c44e979ee0df0543ea459502` | `8519056d5b9484eb0cc4dcf9f693285b4e65518a` | True |
| #112 | merged | `main` / `6780088befd33e711230d570bb291edb2ee40cbf` | `validation/adr-0030-i5-independent-20261019` / `c2032339cd51604ad2232ce1474169930f60ef2b` | `6780088befd33e711230d570bb291edb2ee40cbf` | True |
| #113 | merged | `main` / `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` | `audit/context-provider-agnostic-20261020` / `24f593861327328fa00dab0b83f956cec330a0ac` | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` | True |
| #114 | merged | `main` / `54b9fb0a2fef10c02354ff948e9e2efda6b99d5f` | `docs/generalized-context-resources-20261020` / `a4e3e0fb9c57a53d93f0f9eab93139d4747e4fb8` | `24f593861327328fa00dab0b83f956cec330a0ac` | False |
| #115 | open | `main` / `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` | `experiment/context-u3-cprime-20261021` / `8ab57eb74068f5ba303b5985a335f0f76be4fdd2` | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` | True |
| #116 | merged | `main` / `1ccb7f1902127cde649edcf605bb6d5935427302` | `impl/adr0031-i1a-identity-codec` / `d92377599a50f192f534836fc12402a5fe87ca83` | `1ccb7f1902127cde649edcf605bb6d5935427302` | True |
| #117 | open | `main` / `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` | `impl/adr0031-i1b-resource-key` / `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` | `d92377599a50f192f534836fc12402a5fe87ca83` | False |
| #118 | open | `impl/adr0031-i1b-resource-key` / `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` | `validation/adr0031-i1b-fixtures-20261021` / `9ea69ba8804a368802457950601a5a4027174c52` | `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` | True |
| #119 | open | `validation/adr0031-i1b-fixtures-20261021` / `9ea69ba8804a368802457950601a5a4027174c52` | `docs/adr0031-i1b-independent-review-20261021` / `cb49836aa855da8503f02370b9a60dddac5d6113` | `9ea69ba8804a368802457950601a5a4027174c52` | True |
| #120 | open | `validation/adr0031-i1b-fixtures-20261021` / `9ea69ba8804a368802457950601a5a4027174c52` | `docs/adr0031-i2-preparation-20261021` / `9eaa5111c94204c4adf791cd1565b704728493f1` | `9ea69ba8804a368802457950601a5a4027174c52` | True |
| #121 | open | `docs/adr0031-i2-preparation-20261021` / `9eaa5111c94204c4adf791cd1565b704728493f1` | `review/adr0031-i2-sql-task-d-20261021` / `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6` | `9eaa5111c94204c4adf791cd1565b704728493f1` | True |
| #122 | open | `review/adr0031-i2-sql-task-d-20261021` / `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6` | `design/adr0031-i2-transfer-fence-f1-20261021` / `2199a882d79c9c707fffcba3a8327ef96a3fc384` | `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6` | True |
| #123 | open | `design/adr0031-i2-transfer-fence-f1-20261021` / `2199a882d79c9c707fffcba3a8327ef96a3fc384` | `review/adr0031-i2-cf1-task-f-20261021` / `c1b62d216db2b728a4c8cb1821250335fcafc534` | `2199a882d79c9c707fffcba3a8327ef96a3fc384` | True |
| #124 | open | `review/adr0031-i2-cf1-task-f-20261021` / `c1b62d216db2b728a4c8cb1821250335fcafc534` | `impl/adr0031-i2-resources-task-e-20261021` / `4cb90d35bd9c572239496a24cb0dd62049029235` | `c1b62d216db2b728a4c8cb1821250335fcafc534` | True |
| #125 | open | `impl/adr0031-i2-resources-task-e-20261021` / `4cb90d35bd9c572239496a24cb0dd62049029235` | `review/adr0031-i2-task-g-20261022` / `a54e4432b0514ba5a5fe8e73ddcdbc492f99b95e` | `4cb90d35bd9c572239496a24cb0dd62049029235` | True |
| #126 | open | `review/adr0031-i2-task-g-20261022` / `a54e4432b0514ba5a5fe8e73ddcdbc492f99b95e` | `impl/adr0031-i3-parent-reports-20261022` / `614ccaac3512a0df4291653fc83901df211f00f6` | `a54e4432b0514ba5a5fe8e73ddcdbc492f99b95e` | True |
| #127 | open | `impl/adr0031-i3-parent-reports-20261022` / `614ccaac3512a0df4291653fc83901df211f00f6` | `impl/adr0031-i4-transfer-sql-20261022` / `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e` | `614ccaac3512a0df4291653fc83901df211f00f6` | True |
| #128 | open | `impl/adr0031-i4-transfer-sql-20261022` / `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e` | `review/adr0031-i4-independent-20261022` / `2003a9ee4f25907bcf96a634980b8caffc133c4e` | `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e` | True |
| #129 | open | `review/adr0031-i4-independent-20261022` / `2003a9ee4f25907bcf96a634980b8caffc133c4e` | `impl/adr0031-i5-typed-admission-20261022` / `99e40c9af91f9ea36dd3d4ba97eccad46f6c6e14` | `2003a9ee4f25907bcf96a634980b8caffc133c4e` | True |
| #130 | open | `impl/adr0031-i5-typed-admission-20261022` / `99e40c9af91f9ea36dd3d4ba97eccad46f6c6e14` | `review/adr0031-i5-independent-20261022` / `b4ede5d8a87f3ce7b1f6df8fda5b3051c3865ba2` | `99e40c9af91f9ea36dd3d4ba97eccad46f6c6e14` | True |
| #131 | open | `review/adr0031-i5-independent-20261022` / `b4ede5d8a87f3ce7b1f6df8fda5b3051c3865ba2` | `docs/sqlite-runtime-policy-20261022` / `01b427e392243e06eb9be0e3a50bb09ecacd0d5f` | `b4ede5d8a87f3ce7b1f6df8fda5b3051c3865ba2` | True |
| #132 | open | `docs/sqlite-runtime-policy-20261022` / `01b427e392243e06eb9be0e3a50bb09ecacd0d5f` | `fix/sqlite-runtime-ci-20261022` / `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37` | `01b427e392243e06eb9be0e3a50bb09ecacd0d5f` | True |
| #133 | open | `fix/sqlite-runtime-ci-20261022` / `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37` | `fix/adr0032-host-runtime-20261022` / `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37` | True |
| #134 | open | `fix/adr0032-host-runtime-20261022` / `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `docs/adr0031-i6-boundary-contract-20261022` / `418ee68046fdfd03a0e84cc840e5d52fce176b81` | `f16e5b1713bde9a2f18263a25397c4b450fd5773` | True |
| #135 | open | `fix/adr0032-host-runtime-20261022` / `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `docs/adr0033-minimal-sdist-20261022` / `18ba867d1c2f33c7d17939b2722d22a67139363a` | `f16e5b1713bde9a2f18263a25397c4b450fd5773` | True |
| #136 | open | `fix/adr0032-host-runtime-20261022` / `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `review/c0-hosted-runtime-audit-20261022` / `8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82` | `f16e5b1713bde9a2f18263a25397c4b450fd5773` | True |
| #137 | open | `docs/adr0033-minimal-sdist-20261022` / `217cf2008a10a5911275e5c9d6617586fa017641` | `docs/sdist-review-readiness-20261022` / `7f9c7ad7c418da3b7a638fe20048e13a7701e3d9` | `217cf2008a10a5911275e5c9d6617586fa017641` | True |
| #138 | open | `docs/adr0033-minimal-sdist-20261022` / `18ba867d1c2f33c7d17939b2722d22a67139363a` | `impl/adr0033-minimal-sdist-20261022` / `8cd89a3d25c811ee32d117ec32fe76a6022e6d94` | `18ba867d1c2f33c7d17939b2722d22a67139363a` | True |
| #139 | open | `review/c0-hosted-runtime-audit-20261022` / `8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82` | `fix/c0-e1-receipt-limit-20261023` / `3e2609baa07a9e92c8f2dc4dd1608f311021a1cb` | `8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82` | True |
| #140 | open | `impl/adr0033-minimal-sdist-20261022` / `8cd89a3d25c811ee32d117ec32fe76a6022e6d94` | `review/adr0033-sdist-independent-20261023` / `ef3ca118d4ab5e52dc2d1c7de384c3557509add2` | `8cd89a3d25c811ee32d117ec32fe76a6022e6d94` | True |
| #141 | open | `docs/adr0031-i6-boundary-contract-20261022` / `418ee68046fdfd03a0e84cc840e5d52fce176b81` | `review/adr0031-i6-design-independent-20261023` / `dc6e663ea90e55210ed5674cae6c332f66a4ac18` | `418ee68046fdfd03a0e84cc840e5d52fce176b81` | True |
| #142 | open | `review/adr0033-sdist-independent-20261023` / `ef3ca118d4ab5e52dc2d1c7de384c3557509add2` | `fix/adr0033-sdist-archive-hardening` / `59307c40ea65554736e131cedd00f04c9906551b` | `ef3ca118d4ab5e52dc2d1c7de384c3557509add2` | True |
| #143 | open | `review/adr0031-i6-design-independent-20261023` / `dc6e663ea90e55210ed5674cae6c332f66a4ac18` | `impl/adr0031-i6a-secure-admission` / `f5dc409429cdb69955b55e3c27a7ef3c163762fb` | `dc6e663ea90e55210ed5674cae6c332f66a4ac18` | True |
| #144 | open | `fix/adr0033-sdist-archive-hardening` / `59307c40ea65554736e131cedd00f04c9906551b` | `review/adr0033-hardening-rereview-20261023` / `ededcd83eb2d99a602ba18c8fe3c177125c825ac` | `59307c40ea65554736e131cedd00f04c9906551b` | True |
| #145 | open | `impl/adr0031-i6a-secure-admission` / `f5dc409429cdb69955b55e3c27a7ef3c163762fb` | `fix/adr0031-i6a-regressions-20261023` / `08fbb956c2e470e245146b0dbae747ed0690ea40` | `f5dc409429cdb69955b55e3c27a7ef3c163762fb` | True |
| #146 | open | `fix/adr0031-i6a-regressions-20261023` / `08fbb956c2e470e245146b0dbae747ed0690ea40` | `review/adr0031-i6a-remediation-independent-20261023` / `274645e7dd451e24f324feb81b1591a64ba2a7ab` | `08fbb956c2e470e245146b0dbae747ed0690ea40` | True |
| #147 | open | `fix/c0-e1-receipt-limit-20261023` / `3e2609baa07a9e92c8f2dc4dd1608f311021a1cb` | `review/c0-e1-independent-20261023` / `e7762952e18061de8c8235beaeddf42f20ad9f5a` | `3e2609baa07a9e92c8f2dc4dd1608f311021a1cb` | True |
| #148 | open | `review/adr0031-i6a-remediation-independent-20261023` / `274645e7dd451e24f324feb81b1591a64ba2a7ab` | `fix/adr0031-i6a-originals-binding-20261023` / `268025f67841285d105737b5a0d7bd15b1a6f59c` | `274645e7dd451e24f324feb81b1591a64ba2a7ab` | True |
| #149 | open | `fix/adr0031-i6a-originals-binding-20261023` / `268025f67841285d105737b5a0d7bd15b1a6f59c` | `review/adr0031-i6a-task-c-20261023` / `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00` | `268025f67841285d105737b5a0d7bd15b1a6f59c` | True |

For #137 the API base snapshot and actual merge-base are `217cf2008a10a5911275e5c9d6617586fa017641`, while the current #135 branch resolves to `18ba867d1c2f33c7d17939b2722d22a67139363a`. That current head is not an ancestor of #137. Historical readiness did not incorporate later design acceptance.

Actual ancestry-reduced edges (head commits, not PR numbering or base labels):

```text
#148 -> #149
#146 -> #148
#145 -> #146
#143 -> #145
#142 -> #144
#141 -> #143
#140 -> #142
#139 -> #147
#138 -> #140
#136 -> #139
#135 -> #138
#134 -> #141
#133 -> #137
#133 -> #136
#133 -> #135
#133 -> #134
#132 -> #133
#131 -> #132
#130 -> #131
#129 -> #130
#128 -> #129
#127 -> #128
#126 -> #127
#125 -> #126
#124 -> #125
#123 -> #124
#122 -> #123
#121 -> #122
#120 -> #121
#118 -> #120
#118 -> #119
#117 -> #118
#116 -> #117
#114 -> #116
#113 -> #114
#112 -> #115
#112 -> #113
#111 -> #112
#110 -> #111
#109 -> #110
#108 -> #110
#107 -> #109
#107 -> #108
#106 -> #107
#105 -> #106
#104 -> #105
#103 -> #104
#102 -> #103
#101 -> #102
#100 -> #101
```
