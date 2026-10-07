# Side-Channel-Analysis

ChipWhisperer로 **ML-KEM**(FIPS 203, Kyber)의 부채널 파형을 수집하기 위한 펌웨어와 노트북입니다.
타깃은 **CW308T-STM32F4HWC**(STM32F415RGT6)이고, 암호 구현은 [pqm4](https://github.com/mupq/pqm4)의 코드를
사용합니다(basemul 트리거용 `#ifdef` 한 곳 외에는 수정 없음). ChipWhisperer 빌드 시스템도 레포에 포함되어 있어 레포 하나로 빌드됩니다. 파라미터셋(512/768/1024)과 구현(m4fspeed/m4fstack/clean)은 빌드 옵션으로 고릅니다.

## 구성

`firmware/mcu`와 `jupyter/Setup_Scripts`는 ChipWhisperer와, `firmware/mcu/pqm4`는 pqm4 저장소와 같은 경로 구조입니다.

```
Side-Channel-Analysis/
├── firmware/mcu/                          # = chipwhisperer/firmware/mcu 구조
│   ├── Makefile.inc                       # ChipWhisperer에서 복사
│   ├── crypto/Makefile.crypto             # ChipWhisperer에서 복사
│   ├── simpleserial/                      # ChipWhisperer에서 복사
│   ├── hal/Makefile.hal, hal.c, hal.h     # ChipWhisperer에서 복사
│   ├── hal/chipwhisperer-fw-extra/        # 서브모듈 (STM32F4 HAL)
│   ├── pqm4/                              # = pqm4 저장소 구조 (원본 그대로)
│   │   ├── crypto_kem/ml-kem-{512,768,1024}/{m4fspeed,m4fstack}/
│   │   ├── common/keccakf1600.S
│   │   ├── mupq/common/                   # fips202, randombytes.h, compat.h
│   │   └── mupq/pqclean/crypto_kem/ml-kem-{512,768,1024}/clean/
│   └── simpleserial-mlkem/                # ML-KEM SimpleSerial 펌웨어 (CW의 simpleserial-aes와 같은 위치)
│       ├── Makefile                       # PARAMS / IMPL / TRIGGER 옵션, FIRMWAREPATH = ../.
│       ├── simpleserial-mlkem.c           # 명령 처리(s/c/d/x/i), 전체 트리거, FPU 활성화
│       └── mlkem_api.h                    # clean(PQClean) 심볼 이름 매핑
├── jupyter/                               # = chipwhisperer/jupyter 구조
│   ├── Setup_Scripts/Setup_Generic.ipynb  # ChipWhisperer에서 복사 (scope/target/prog/reset_target)
│   └── mlkem-test.ipynb                   # 빌드 → 플래시 → 기능 검증 → 파형 수집
├── tools/
│   ├── verify_emu.py                      # 보드 없이 ELF를 에뮬레이터로 검증
│   ├── import_pqm4.sh                     # pqm4에서 firmware/mcu/pqm4 다시 가져오기
│   └── import_chipwhisperer.sh            # ChipWhisperer 빌드 파일 다시 가져오기
└── requirements.txt
```

## 준비물

레포 밖에서 따로 준비해야 하는 것입니다.

| 구분 | 내용 | 설치 |
|---|---|---|
| 하드웨어 | ChipWhisperer(CW-Lite/Pro/Husky), CW308 UFO, CW308T-STM32F4HWC(일반 STM32F4 타깃도 동일) | |
| ARM 툴체인 | `arm-none-eabi-gcc`, newlib, `make` | WSL(Ubuntu): `sudo apt install -y gcc-arm-none-eabi libnewlib-arm-none-eabi make` |
| Python 패키지 | chipwhisperer, kyber-py, numpy, matplotlib, tqdm (+ 검증 스크립트용 unicorn, pyelftools) | `pip install -r requirements.txt` |
| Jupyter | 노트북의 `%%bash` 셀에서 `make`와 `arm-none-eabi-gcc`가 실행되는 환경 (ChipWhisperer 강의 노트북과 같은 조건) | ChipWhisperer 설치 환경 그대로 사용 |

## 클론

서브모듈(STM32F4 HAL)까지 함께 받아야 빌드됩니다.

```bash
git clone --recursive --shallow-submodules https://github.com/heahgo/Side-Channel-Analysis.git
```

서브모듈 없이 클론했다면 레포 안에서 다음을 실행하세요.

```bash
git submodule update --init --depth 1
```

ChipWhisperer 빌드 시스템 파일은 `firmware/mcu`에 들어 있고, STM32F4 HAL만 서브모듈
`firmware/mcu/hal/chipwhisperer-fw-extra`(`5bcd583`, 약 200MB)로 받습니다. 바깥에 ChipWhisperer 저장소가 없어도 빌드됩니다.

## 빌드 (WSL)

```bash
sudo apt install -y gcc-arm-none-eabi libnewlib-arm-none-eabi make

cd firmware/mcu/simpleserial-mlkem
make PLATFORM=CW308_STM32F4                                       # ML-KEM-768, m4fstack, full 트리거
make PLATFORM=CW308_STM32F4 TRIGGER=basemul                       # ML-KEM-768 m4fstack, basemul 트리거
make PLATFORM=CW308_STM32F4 PARAMS=1024 IMPL=clean                # ML-KEM-1024, PQClean 레퍼런스
```

| 옵션 | 값 | 기본값 | 설명 |
|---|---|---|---|
| `PARAMS` | `512` `768` `1024` | `768` | ML-KEM 파라미터셋 |
| `IMPL` | `m4fstack` `m4fspeed` `clean` | `m4fstack` | pqm4 구현 |
| `TRIGGER` | `full` `basemul` | `full` | 트리거 구간 (`basemul`은 `PARAMS=768 IMPL=m4fstack`만) |
| `SS_VER` | `SS_VER_1_1` 등 | `SS_VER_1_1` | SimpleSerial 버전(호스트와 맞출 것) |
| `OPT` | `0` `1` `2` `3` `s` | `s` | 컴파일 최적화 수준(`-O<값>`). pqm4 기본은 `3`, CW 기본은 `s`. 논문 비교용은 `OPT=3` |

> 어셈블리(NTT, basemul, Keccak)는 `OPT`의 영향을 받지 않지만 주변 C 코드의 명령 순서와 누설 위치가 달라집니다.
> pqm4를 타깃으로 한 다른 연구와 조건을 맞추려면 `OPT=3`으로 빌드하세요. 노트북은 기본으로 `OPT = "3"`을 씁니다.

출력 파일 이름은 `simpleserial-mlkem<PARAMS>-<IMPL>[-basemul]-CW308_STM32F4.hex`입니다.
CW 빌드 시스템의 `make`는 매번 전체를 다시 빌드하므로, 옵션을 바꿀 때 `make clean`이 필요 없습니다.

### 구현

| `IMPL` | pqm4 경로 | 특징 |
|---|---|---|
| `m4fspeed` | `crypto_kem/ml-kem-*/m4fspeed` | Cortex-M4F 속도 최적화. basemul 사전 계산값을 캐시해 가장 빠름 |
| `m4fstack` | `crypto_kem/ml-kem-*/m4fstack` | Cortex-M4F 스택 최적화([Huang et al., ePrint 2022/956](https://eprint.iacr.org/2022/956)). 캐시 없이 행렬 A를 즉석 생성 |
| `clean` | `mupq/pqclean/crypto_kem/ml-kem-*/clean` | PQClean 순수 C 레퍼런스. 어셈블리 없음, Montgomery 리덕션 |

두 m4f 구현은 NTT, basemul, Keccak이 어셈블리이고, 16비트 계수 두 개를 32비트 레지스터에 묶어 계산하며
Plantard 리덕션을 씁니다. 누설 모델이 `clean`과 다르니 주의하세요. 세 구현 모두 마스킹은 없습니다.

### 트리거

| `TRIGGER` | 구간 | 위치 |
|---|---|---|
| `full` | `crypto_kem_dec` 전체(재암호화 포함) | `simpleserial-mlkem.c`의 `do_dec()` |
| `basemul` | `indcpa_dec`의 첫 비밀키 basemul(비밀키 첫 다항식 × NTT(u₀)) | `pqm4/crypto_kem/ml-kem-768/m4fstack/indcpa.c`의 `poly_frombytes_mul(&mp, &mp, sk)` |

basemul 트리거는 pqm4 `ml-kem-768/m4fstack/indcpa.c`에 `#ifdef MLKEM_TRIGGER_BASEMUL`로
`trigger_high()`/`trigger_low()`를 넣은 것이며, 이 조합에서만 지원합니다(다른 조합은 `make`가 오류를 냅니다).
`indcpa_dec` 안에 있으므로 재암호화 중의 basemul은 표시되지 않습니다. 다른 연산을 노리려면 이 `#ifdef` 위치를 옮기면 됩니다.

### 측정값 (에뮬레이터 명령어 수, arm-none-eabi-gcc 13.3)

| 파라미터 | 구현 | `crypto_kem_dec` | basemul 트리거 구간 | 플래시 |
|---|---|---|---|---|
| 512 | m4fspeed | 39만 | 2,072 | 26KB |
| 512 | m4fstack | 39만 | 2,584 | 24KB |
| 512 | clean | 76만 | 10,454 | 16KB |
| 768 | m4fspeed | 64만 | 2,072 | 26KB |
| 768 | m4fstack | 65만 | 2,584 | 24KB |
| 768 | clean | 118만 | 10,454 | 16KB |
| 1024 | m4fspeed | 98만 | 2,072 | 27KB |
| 1024 | m4fstack | 100만 | 2,584 | 24KB |
| 1024 | clean | 170만 | 10,454 | 17KB |

명령어 수는 사이클 수와 정확히 같지 않지만 규모는 비슷합니다. ADC는 타깃 클럭의 4배이므로 필요한 샘플 수는 대략 사이클 × 4입니다.
CW-Lite(최대 약 24k 샘플)로는 m4f의 basemul 구간은 다 담기지만, `clean` basemul과 `full`은 앞부분만 담깁니다.

## 플래시와 테스트

`jupyter/mlkem-test.ipynb`를 위에서부터 실행합니다.

1. **설정**: `PARAMS`, `IMPL`, `TRIGGER`
2. **연결**: CW 강의 노트북처럼 `%run "Setup_Scripts/Setup_Generic.ipynb"`로 `scope`, `target`, `prog`, `reset_target(scope)`를 만듭니다(`default_setup()`: 7.37MHz 클럭, ADC = 4배 클럭).
3. **빌드·플래시**: CW 강의 노트북처럼 `%%bash -s "$PLATFORM" ...` 셀에서 `make`를 실행하고, 만들어진 hex를 `cw.program_target(scope, prog, ...)`로 플래시합니다. ST-Link는 필요 없습니다.
4. **기능 검증**: `i` 명령으로 플래시된 펌웨어가 설정과 같은지 확인하고, `kyber-py`로 만든 암호문의 복호화 결과를 비교합니다. 변조된 암호문(implicit rejection)도 확인합니다.
5. **파형 1개**: 파형을 그리고 `scope.adc.trig_count`로 트리거 구간 길이를 확인합니다.
6. **대량 수집**: 고정 비밀키와 무작위 암호문으로 `N_TRACES`개를 수집해 레포 최상위 `traces/*.npz`로 저장합니다.

## 펌웨어 프로토콜 (SimpleSerial 1.1)

| 명령 | 페이로드 | 동작 |
|---|---|---|
| `s` | 129바이트 = 조각 번호 1 + 데이터 128 | 비밀키(dk) 조각 적재 |
| `c` | 129바이트 = 조각 번호 1 + 데이터 128 | 암호문 조각 적재 |
| `d` | 0바이트 | `crypto_kem_dec` 실행 후 `r`로 공유 비밀 32바이트 반환 |
| `x` | 0바이트 | 비밀키·암호문 버퍼 초기화 |
| `i` | 0바이트 | `r` 4바이트: 파라미터/256, 구현(1=m4fstack, 2=m4fspeed, 3=clean), 트리거(0=full, 1=basemul), 조각 크기 |

| 파라미터 | 비밀키 dk | 암호문 |
|---|---|---|
| 512 | 1632바이트 (13조각) | 768바이트 (6조각) |
| 768 | 2400바이트 (19조각) | 1088바이트 (9조각) |
| 1024 | 3168바이트 (25조각) | 1568바이트 (13조각) |

SimpleSerial 1.1은 고정 길이라 마지막 조각도 0으로 채워 129바이트로 보냅니다.
비밀키와 암호문은 FIPS 203 바이트 형식 그대로이며, `kyber-py`의 `dk`, `ct`를 그대로 보내면 됩니다.

## 보드 없이 검증

빌드한 ELF의 `crypto_kem_dec`를 Unicorn(Cortex-M4) 에뮬레이터로 실행해 `kyber-py` 결과와 비교합니다.
basemul 빌드는 트리거 GPIO가 정확히 한 번 올라갔다 내려가는지와 구간 길이도 확인합니다.

```bash
pip install unicorn pyelftools kyber-py
python tools/verify_emu.py firmware/mcu/simpleserial-mlkem/simpleserial-mlkem768-m4fstack-basemul-CW308_STM32F4.elf -n 10
```

파라미터셋은 파일 이름에서 읽고, 다르면 `-p 512`처럼 지정합니다.

## 외부 코드 갱신

`firmware/mcu/pqm4`는 pqm4 `5e5cc76`(mupq `ddccced`)에서, ChipWhisperer 빌드 파일은 ChipWhisperer `0d2492d`에서, `Setup_Generic.ipynb`는 그 커밋이 가리키는 chipwhisperer-jupyter `778289d`에서 가져왔습니다.
버전은 `firmware/mcu/pqm4/VERSION`, `firmware/mcu/CHIPWHISPERER_VERSION`에 있습니다.
pqm4는 구현 사이에 심볼릭 링크를 많이 쓰는데 Windows에서 체크아웃하면 깨지므로, 서브모듈 대신 실제 파일로 풀어 넣었습니다.

```bash
git clone --recursive https://github.com/mupq/pqm4.git /tmp/pqm4
tools/import_pqm4.sh /tmp/pqm4                        # firmware/mcu/pqm4

git clone --depth 1 https://github.com/newaetech/chipwhisperer.git /tmp/cw
tools/import_chipwhisperer.sh /tmp/cw                 # Makefile.inc, hal/, simpleserial/, Setup_Generic.ipynb
```

ChipWhisperer를 갱신하면 `chipwhisperer-fw-extra` 서브모듈도 그 커밋이 가리키는 버전으로 맞추세요.

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `STM32F4 HAL missing` | 서브모듈 미초기화 → `git submodule update --init --depth 1` |
| 어셈블러가 `vmov` 등을 거부 | `ASFLAGS += -mfpu=fpv4-sp-d16` 누락 |
| 복호화 중 HardFault(응답 없음) | FPU(CPACR) 비활성 |
| `ack 없음` / 응답 타임아웃 | 펌웨어와 호스트의 `SS_VER` 불일치, 조각을 129바이트로 채우지 않음 |
| 노트북에서 "펌웨어가 설정과 다릅니다" | 다른 옵션으로 빌드한 hex가 플래시됨 → 2·3단계 다시 실행 |
| 공유 비밀 불일치 | `tools/verify_emu.py`로 ELF부터 검증 |

## 코드 출처

| 구분 | 파일 |
|---|---|
| pqm4 원본 그대로 | `firmware/mcu/pqm4/` (`VERSION` 제외, `crypto_kem/ml-kem-768/m4fstack/indcpa.c`에 트리거 `#ifdef` 추가) |
| ChipWhisperer 원본 그대로 | `firmware/mcu/Makefile.inc`, `crypto/Makefile.crypto`, `hal/Makefile.hal`, `hal/PLATFORM_INCLUDE.mk`, `hal/hal.c`, `hal/hal.h`, `simpleserial/`, `jupyter/Setup_Scripts/Setup_Generic.ipynb` |
| 서브모듈 | `firmware/mcu/hal/chipwhisperer-fw-extra` |
| 이 저장소에서 작성 | `firmware/mcu/simpleserial-mlkem/`, `jupyter/mlkem-test.ipynb`, `tools/` |

- ML-KEM 구현: [pqm4](https://github.com/mupq/pqm4), [PQClean](https://github.com/PQClean/PQClean). 각 파일의 라이선스는 원본을 따릅니다(clean 폴더의 `LICENSE` 참고).
- 빌드 시스템과 HAL: [ChipWhisperer](https://github.com/newaetech/chipwhisperer)(Apache-2.0, `firmware/mcu/LICENSE-chipwhisperer.txt`), [chipwhisperer-fw-extra](https://github.com/newaetech/chipwhisperer-fw-extra)
- 호스트 측 ML-KEM: [kyber-py](https://github.com/GiacomoPope/kyber-py)
