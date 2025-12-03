try:
    import sys
    import os
    from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QRadioButton, QComboBox, QScrollArea, QApplication, QMessageBox
    from PyQt5.QtCore import Qt
    import json
    import random
    import time
    import urllib.request
    import urllib.error
except ImportError as e:
    print(f"필요한 모듈을 찾을 수 없습니다: {e}")
    sys.exit(1)

class DifficultyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cleared_songs = self.loadClearedSongs()  # (구버전) 클리어한 곡들을 불러옴
        self.shown_songs = self.loadShownSongs()  # 각 난이도별로 이미 표시한 곡들을 저장
        self.songs_cache = None  # 곡 데이터 캐시
        self.songs_cache_time = 0  # 캐시 생성 시간
        self.cache_timeout = 300  # 캐시 유효 시간 (초)
        self.songs_url = "https://v-archive.net/db/songs.json"  # 온라인 곡 데이터 URL
        self.last_update_check = 0  # 마지막 업데이트 확인 시간
        self.update_check_interval = 3600  # 업데이트 확인 간격 (1시간)
        self.last_settings = self.loadLastSettings()  # 마지막 설정 불러오기
        self.current_candidates = []  # 현재 추천 후보곡 목록
        self.failed_songs = {}  # 실패한 곡 추적 (난이도별)
        self.result_stats = self.loadResultStats()  # 난이도별 성공/실패 집계
        self.attempt_stats = self.loadAttemptStats()  # 곡+패턴별 시도 집계 (표시용 고유 통계)
        self.cleanExistingDuplicates()  # 기존 중복 데이터 정리
        self.migrateClearedToAttemptStats()  # 구버전 클리어 정보를 attempt_stats로 이전
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('DJMAX RESPECT V 업다운 순회')
        self.setGeometry(100, 100, 500, 400)  # 높이를 늘려서 새로운 UI 요소들 수용
        
        # 중앙 위젯 설정
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(5)  # 위젯 간 간격을 더 줄임
        layout.setContentsMargins(10, 10, 10, 10)  # 여백을 더 줄임
        
        # 키 모드 선택
        mode_group = QHBoxLayout()
        mode_group.setSpacing(5)  # 라디오 버튼 간 간격
        self.mode_buttons = {}
        for mode in ['4B', '5B', '6B', '8B']:
            btn = QRadioButton(mode)
            self.mode_buttons[mode] = btn
            mode_group.addWidget(btn)
        
        # 마지막 사용한 모드가 있으면 선택, 없으면 기본값 4B
        last_mode = self.last_settings.get('last_mode', '4B')
        self.mode_buttons[last_mode].setChecked(True)
        
        layout.addLayout(mode_group)
        
        # 난이도 선택
        level_layout = QHBoxLayout()
        level_layout.setSpacing(5)
        level_layout.addWidget(QLabel('난이도:'))
        self.level_combo = QComboBox()
        self.updateLevelCombo()
        
        # 현재 선택된 모드의 마지막 난이도 설정
        current_mode = self.getSelectedMode()
        last_level = self.last_settings.get(current_mode, 8.1)
        last_level_index = self.level_combo.findText(f"{last_level:.1f}")
        if last_level_index >= 0:
            self.level_combo.setCurrentIndex(last_level_index)
            
        level_layout.addWidget(self.level_combo)
        layout.addLayout(level_layout)
        
        # 시작 버튼
        self.start_btn = QPushButton('시작')
        self.start_btn.clicked.connect(self.onStart)
        layout.addWidget(self.start_btn)
        
        # 현재 난이도 표시
        self.level_label = QLabel(f'현재 난이도: {last_level:.1f}')
        self.level_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.level_label)
        
        # 진행도 표시
        self.progress_label = QLabel('진행도: -/-')
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        # 성공/실패 통계 표시
        self.sf_label = QLabel('')
        self.sf_label.setAlignment(Qt.AlignCenter)
        self.sf_label.setTextFormat(Qt.RichText)
        self.sf_label.setText("<b><span style='color:#2e7d32'>성공: 0</span></b> / <b><span style='color:#d32f2f'>실패: 0</span></b>")
        layout.addWidget(self.sf_label)
        
        # 실패한 난이도 표시
        self.failed_levels_label = QLabel('')
        self.failed_levels_label.setAlignment(Qt.AlignCenter)
        self.failed_levels_label.setTextFormat(Qt.RichText)
        self.failed_levels_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
        layout.addWidget(self.failed_levels_label)
        
        # 진행도 초기화 버튼들 추가
        reset_btn_layout = QHBoxLayout()
        self.reset_current_btn = QPushButton('현재 난이도 초기화')
        self.reset_all_btn = QPushButton('전체 모드 초기화')
        self.reset_current_btn.clicked.connect(self.onResetCurrentLevel)
        self.reset_all_btn.clicked.connect(self.onResetAllLevels)
        reset_btn_layout.addWidget(self.reset_current_btn)
        reset_btn_layout.addWidget(self.reset_all_btn)
        layout.addLayout(reset_btn_layout)
        
        
        # 성공/실패 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)
        self.success_btn = QPushButton('성공')
        self.fail_btn = QPushButton('실패')
        self.success_btn.clicked.connect(self.onSuccess)
        self.fail_btn.clicked.connect(self.onFail)
        btn_layout.addWidget(self.success_btn)
        btn_layout.addWidget(self.fail_btn)
        layout.addLayout(btn_layout)
        
        # 클리어 체크박스와 초기화 버튼을 같은 줄에 배치
        clear_layout = QHBoxLayout()
        self.clear_checkbox = QCheckBox('이 곡 클리어 완료')
        self.clear_checkbox.stateChanged.connect(self.onClearCheck)
        clear_layout.addWidget(self.clear_checkbox)
        
        self.reset_btn = QPushButton('클리어 초기화')
        self.reset_btn.clicked.connect(self.onResetClears)
        clear_layout.addWidget(self.reset_btn)
        layout.addLayout(clear_layout)
        
        # 추천 곡 목록 (스크롤 가능한 영역으로 변경)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.song_list = QLabel('추천 곡이 여기에 표시됩니다')
        self.song_list.setWordWrap(True)
        self.song_list.setAlignment(Qt.AlignCenter)
        scroll_content.setLayout(QVBoxLayout())
        scroll_content.layout().setContentsMargins(5, 5, 5, 5)  # 스크롤 영역 내부 여백
        scroll_content.layout().addWidget(self.song_list)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # 버튼 초기 상태
        self.success_btn.setEnabled(False)
        self.fail_btn.setEnabled(False)
        self.clear_checkbox.setEnabled(False)
        
        # 현재 난이도 설정 (선택된 모드의 마지막 사용 난이도)
        self.current_level = last_level
        self.current_song = None
        self.current_pattern = None
        
        # 모든 UI 요소가 생성된 후에 모드 변경 이벤트 연결
        for mode, btn in self.mode_buttons.items():
            btn.toggled.connect(self.onModeChanged)
        
        
    def updateSongsData(self):
        """온라인에서 곡 데이터를 업데이트합니다. (메시지 없음)"""
        try:
            # 온라인에서 데이터 다운로드
            print("온라인에서 곡 데이터를 다운로드하는 중...")
            with urllib.request.urlopen(self.songs_url, timeout=30) as response:
                online_data = json.loads(response.read().decode('utf-8'))
            
            # 필요한 필드만 필터링
            filtered_data = []
            excluded_fields = ["title", "dlcCode", "dlc"]
            
            for song in online_data:
                filtered_song = {}
                for key, value in song.items():
                    if key not in excluded_fields:
                        filtered_song[key] = value
                # patterns 내부의 rating도 제거
                if "patterns" in filtered_song:
                    for mode in filtered_song["patterns"].values():
                        for diff in mode.values():
                            if isinstance(diff, dict) and "rating" in diff:
                                del diff["rating"]
                filtered_data.append(filtered_song)
            
            # 로컬 파일에 저장
            script_dir = os.path.dirname(os.path.abspath(__file__))
            songs_path = os.path.join(script_dir, 'songs.json')
            
            with open(songs_path, 'w', encoding='utf-8') as f:
                json.dump(filtered_data, f, ensure_ascii=False, indent=2)
            
            # 캐시 초기화 (새로운 데이터를 사용하도록)
            self.songs_cache = None
            self.songs_cache_time = 0
            
            print(f"곡 데이터 업데이트 완료: {len(filtered_data)}곡")
            return True
            
        except urllib.error.URLError as e:
            print(f"네트워크 오류: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            return False
        except Exception as e:
            print(f"업데이트 중 오류 발생: {e}")
            return False
            
    def checkForAutoUpdate(self):
        """자동 업데이트 확인 (1시간마다)"""
        current_time = time.time()
        if (current_time - self.last_update_check) > self.update_check_interval:
            self.last_update_check = current_time
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                songs_path = os.path.join(script_dir, 'songs.json')
                
                # 로컬 파일이 없거나 24시간 이상 오래된 경우 자동 업데이트
                if not os.path.exists(songs_path):
                    print("로컬 곡 데이터가 없어 자동 업데이트를 시도합니다.")
                    self.updateSongsData()
                else:
                    file_age = current_time - os.path.getmtime(songs_path)
                    if file_age > 86400:  # 24시간 = 86400초
                        print("곡 데이터가 24시간 이상 오래되어 자동 업데이트를 시도합니다.")
                        self.updateSongsData()
            except Exception as e:
                print(f"자동 업데이트 확인 중 오류: {e}")
                
    def onModeChanged(self):
        """모드가 변경될 때 해당 모드의 마지막 난이도로 콤보박스를 업데이트합니다."""
        try:
            # 선택된 라디오 버튼만 처리
            sender = self.sender()
            if sender and sender.isChecked():
                current_mode = self.getSelectedMode()
                last_level = self.last_settings.get(current_mode, 8.1)
                
                # 콤보박스를 해당 모드의 마지막 난이도로 설정
                last_level_index = self.level_combo.findText(f"{last_level:.1f}")
                if last_level_index >= 0:
                    self.level_combo.setCurrentIndex(last_level_index)
                
                # 현재 난이도와 라벨 업데이트
                self.current_level = last_level
                self.level_label.setText(f'현재 난이도: {last_level:.1f}')
                
        except Exception as e:
            print(f"모드 변경 중 오류: {e}")
        
    def checkAndDisplayFailedLevels(self):
        """현재 모드에서 모든 곡을 실패한 난이도들을 확인하고 표시합니다."""
        try:
            songs = self.loadSongsData()
            if songs is None:
                return
                
            mode = self.getSelectedMode()
            failed_levels = []
            
            # 모든 난이도에 대해 확인
            levels = [1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3,
                     4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3,
                     7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3,
                     10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3,
                     13.1, 13.2, 13.3, 14.1, 14.2, 14.3, 15.1, 15.2, 15.3,
                     16.1, 16.2]
            
            for level in levels:
                level_key = f"{mode}_{level:.1f}"
                candidate_set = set()
                
                # 해당 난이도의 모든 후보 곡 수집
                attempt_level = self.attempt_stats.get(level_key, {})
                for song in songs:
                    if mode in song.get('patterns', {}):
                        patterns = song['patterns'][mode]
                        for diff_type, info in patterns.items():
                            if isinstance(info, dict) and 'floor' in info:
                                if abs(info['floor'] - level) < 0.01:
                                    song_key = f"{song['name']}_{mode}_{diff_type}"
                                    stats = attempt_level.get(song_key, {})
                                    if not stats.get('cleared', False):
                                        candidate_set.add((song['name'], diff_type))
                
                # 해당 난이도의 실패한 곡들
                failed_set = self.failed_songs.get(level_key, set())
                
                # 모든 후보 곡을 실패했으면 실패한 난이도로 표시
                if candidate_set and candidate_set.issubset(failed_set):
                    failed_levels.append(f"{level:.1f}")
            
            # 실패한 난이도 표시 업데이트
            if failed_levels:
                self.failed_levels_label.setText(f"⚠️ 모든 곡 실패한 난이도: {', '.join(failed_levels)}")
            else:
                self.failed_levels_label.setText("")
                
        except Exception as e:
            print(f"실패한 난이도 확인 중 오류: {e}")
        
    def loadClearedSongs(self):
        """구버전 호환용: 기존 cleared_songs.json을 로드합니다. (마이그레이션 후에는 비워짐)"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cleared_path = os.path.join(script_dir, 'cleared_songs.json')
            if os.path.exists(cleared_path):
                with open(cleared_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception:
            return {}
    
    def migrateClearedToAttemptStats(self):
        """구버전 cleared_songs.json 내용을 attempt_stats로 옮기고 cleared_songs를 비웁니다."""
        try:
            if not self.cleared_songs:
                return
            
            # cleared_songs의 key는 f\"{song_name}_{mode}_{pattern}\" 형식
            for song_key in list(self.cleared_songs.keys()):
                try:
                    # song_key에서 모드와 패턴을 분리
                    parts = song_key.rsplit('_', 2)
                    if len(parts) != 3:
                        continue
                    song_name, mode, pattern = parts
                    
                    # songs.json에서 floor(난이도 값)를 찾아 level_key 구성
                    songs = self.loadSongsData()
                    if not songs:
                        continue
                    level_value = None
                    for song in songs:
                        if song.get('name') != song_name:
                            continue
                        pats = song.get('patterns', {})
                        if mode not in pats:
                            continue
                        info = pats[mode].get(pattern)
                        if isinstance(info, dict) and 'floor' in info:
                            level_value = float(info['floor'])
                            break
                    if level_value is None:
                        continue
                    
                    level_key = f"{mode}_{level_value:.1f}"
                    if level_key not in self.attempt_stats:
                        self.attempt_stats[level_key] = {}
                    if song_key not in self.attempt_stats[level_key]:
                        self.attempt_stats[level_key][song_key] = {'success': 0, 'fail': 0}
                    # cleared 플래그 추가 (불리언으로 저장)
                    self.attempt_stats[level_key][song_key]['cleared'] = True
                except Exception:
                    continue
            
            # 저장 및 기존 cleared_songs 정리
            self.saveAttemptStats()
            self.cleared_songs = {}
        except Exception as e:
            print(f"클리어 정보 마이그레이션 중 오류: {e}")
            
    def loadShownSongs(self):
        """표시된 곡 진행상황을 로드합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            shown_path = os.path.join(script_dir, 'shown_songs.json')
            if os.path.exists(shown_path):
                with open(shown_path, 'r', encoding='utf-8') as f:
                    shown_data = json.load(f)
                    result = {}
                    for level_key, songs in shown_data.items():
                        result[level_key] = set(tuple(song) for song in songs)
                    return result
            return {}
        except Exception as e:
            print(f"표시된 곡 로드 중 오류 발생: {e}")
            return {}
    
    def loadLastSettings(self):
        """마지막 사용 설정을 불러옵니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            settings_path = os.path.join(script_dir, 'last_settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # 기존 형식 호환성을 위한 마이그레이션
                    if 'level' in settings and 'mode' in settings:
                        # 기존 형식을 새 형식으로 변환
                        old_mode = settings['mode']
                        old_level = settings['level']
                        new_settings = {
                            'last_mode': old_mode,
                            old_mode: old_level,
                            '4B': 8.1, '5B': 8.1, '6B': 8.1, '8B': 8.1
                        }
                        new_settings[old_mode] = old_level
                        return new_settings
                    return settings
            # 기본값: 모든 모드를 8.1로 설정
            return {'last_mode': '4B', '4B': 8.1, '5B': 8.1, '6B': 8.1, '8B': 8.1}
        except Exception as e:
            print(f"마지막 설정 로드 중 오류 발생: {e}")
            return {'last_mode': '4B', '4B': 8.1, '5B': 8.1, '6B': 8.1, '8B': 8.1}
            
    def saveLastSettings(self):
        """현재 설정을 저장합니다."""
        try:
            current_mode = self.getSelectedMode()
            # 현재 모드의 난이도를 업데이트
            self.last_settings['last_mode'] = current_mode
            
            # current_level이 설정되어 있을 때만 난이도 저장
            if hasattr(self, 'current_level') and self.current_level is not None:
                self.last_settings[current_mode] = self.current_level
            
            
            script_dir = os.path.dirname(os.path.abspath(__file__))
            settings_path = os.path.join(script_dir, 'last_settings.json')
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.last_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # 오류를 조용히 처리 (사용자에게 메시지 박스로 표시하지 않음)
            pass
            
    def saveClearedSongs(self):
        """구버전 호환용: 더 이상 사용하지 않음 (빈 함수)."""
        pass
            
    def saveShownSongs(self):
        """표시된 곡 진행상황을 저장합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            shown_path = os.path.join(script_dir, 'shown_songs.json')

            # set 타입은 JSON으로 직렬화할 수 없으므로 리스트로 변환
            shown_data = {}
            for level_key, songs in self.shown_songs.items():
                shown_data[level_key] = [list(song) for song in songs]

            with open(shown_path, 'w', encoding='utf-8') as f:
                json.dump(shown_data, f, ensure_ascii=False, indent=2)

            print(f"진행도 저장 완료: {len(shown_data)}개 난이도")

        except Exception as e:
            print(f"표시된 곡 저장 중 오류 발생: {e}")

    def loadResultStats(self):
        """난이도별 성공/실패 통계를 로드합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            stats_path = os.path.join(script_dir, 'result_stats.json')
            if os.path.exists(stats_path):
                with open(stats_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"성공/실패 통계 로드 중 오류: {e}")
            return {}

    def saveResultStats(self):
        """난이도별 성공/실패 통계를 저장합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            stats_path = os.path.join(script_dir, 'result_stats.json')
            with open(stats_path, 'w', encoding='utf-8') as f:
                json.dump(self.result_stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"성공/실패 통계 저장 중 오류: {e}")

    def loadAttemptStats(self):
        """곡+패턴별 시도 통계를 로드합니다. (UI에는 직접 표기하지 않음)"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            stats_path = os.path.join(script_dir, 'attempt_stats.json')
            if os.path.exists(stats_path):
                with open(stats_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"시도 통계 로드 중 오류: {e}")
            return {}

    def saveAttemptStats(self):
        """곡+패턴별 시도 통계를 저장합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            stats_path = os.path.join(script_dir, 'attempt_stats.json')
            with open(stats_path, 'w', encoding='utf-8') as f:
                json.dump(self.attempt_stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"시도 통계 저장 중 오류: {e}")

    def _incrementResult(self, level_key, kind):
        """현재 난이도 레벨키에 대해 성공/실패 카운트를 증가시킵니다."""
        if level_key not in self.result_stats:
            self.result_stats[level_key] = {'success': 0, 'fail': 0}
        if kind == 'success':
            self.result_stats[level_key]['success'] += 1
        elif kind == 'fail':
            self.result_stats[level_key]['fail'] += 1
        self.saveResultStats()

    def _incrementAttempt(self, mode, level_value, song_name, pattern, kind):
        """곡+패턴별 시도 통계를 증가시킵니다.
        구조: attempt_stats[level_key][song_key] = { 'success': n, 'fail': n }
        level_key = f"{mode}_{level:.1f}", song_key = f"{song}_{mode}_{pattern}"
        """
        try:
            level_key = f"{mode}_{level_value:.1f}"
            song_key = f"{song_name}_{mode}_{pattern}"
            
            if level_key not in self.attempt_stats:
                self.attempt_stats[level_key] = {}
            
            if song_key not in self.attempt_stats[level_key]:
                self.attempt_stats[level_key][song_key] = {'success': 0, 'fail': 0}
            
            # success/fail 값은 0 또는 1까지만 올라가도록 제한
            if kind == 'success':
                current = int(self.attempt_stats[level_key][song_key].get('success', 0))
                self.attempt_stats[level_key][song_key]['success'] = 1 if current > 0 else 1
            elif kind == 'fail':
                current = int(self.attempt_stats[level_key][song_key].get('fail', 0))
                self.attempt_stats[level_key][song_key]['fail'] = 1 if current > 0 else 1
            self.saveAttemptStats()
        except Exception:
            pass
    
    def _removeDuplicateSongs(self, level_key, song_name, mode):
        """특정 곡의 중복된 항목들을 제거합니다."""
        try:
            if level_key not in self.attempt_stats:
                return
            
            # 같은 곡명으로 시작하는 모든 키 찾기
            keys_to_remove = []
            for key in self.attempt_stats[level_key].keys():
                if key.startswith(f"{song_name}_{mode}_"):
                    keys_to_remove.append(key)
            
            # 중복이 있으면 첫 번째 것만 남기고 나머지 제거
            if len(keys_to_remove) > 1:
                # 성공이 있으면 성공 우선, 없으면 실패 기록 유지
                has_success = any(self.attempt_stats[level_key][key].get('success', 0) > 0 for key in keys_to_remove)
                
                if has_success:
                    # 성공이 있으면 성공 기록만 유지 (실패 기록 제거)
                    final_stats = {'success': 1, 'fail': 0}
                else:
                    # 성공이 없으면 실패 기록 합산
                    total_fail = sum(self.attempt_stats[level_key][key].get('fail', 0) for key in keys_to_remove)
                    final_stats = {'success': 0, 'fail': min(total_fail, 1)}  # 최대 1로 제한
                
                # 첫 번째 키에 최종 통계 저장
                first_key = keys_to_remove[0]
                self.attempt_stats[level_key][first_key] = final_stats
                
                # 나머지 키들 제거
                for key in keys_to_remove[1:]:
                    del self.attempt_stats[level_key][key]
                
                print(f"중복 제거: {level_key} - {song_name} ({len(keys_to_remove)-1}개 중복 제거)")
                
        except Exception as e:
            print(f"중복 제거 중 오류: {e}")
    
    def cleanExistingDuplicates(self):
        """프로그램 시작 시 기존 중복 데이터를 정리합니다."""
        try:
            cleaned_count = 0
            for level_key, songs in self.attempt_stats.items():
                # 곡명별로 그룹화
                song_groups = {}
                for song_key, stats in songs.items():
                    # 곡명 추출 (첫 번째 _ 이전 부분)
                    song_name = song_key.split('_')[0]
                    if song_name not in song_groups:
                        song_groups[song_name] = []
                    song_groups[song_name].append((song_key, stats))
                
                # 중복이 있는 곡들 정리
                for song_name, song_list in song_groups.items():
                    if len(song_list) > 1:
                        # 성공이 있으면 성공 우선, 없으면 실패 기록 유지
                        has_success = any(stats.get('success', 0) > 0 for _, stats in song_list)
                        
                        if has_success:
                            # 성공이 있으면 성공 기록만 유지 (실패 기록 제거)
                            final_stats = {'success': 1, 'fail': 0}
                            print(f"중복 정리: {level_key} - {song_name} (성공 기록 우선, 실패 기록 제거)")
                        else:
                            # 성공이 없으면 실패 기록 합산
                            total_fail = sum(stats.get('fail', 0) for _, stats in song_list)
                            final_stats = {'success': 0, 'fail': min(total_fail, 1)}  # 최대 1로 제한
                            print(f"중복 정리: {level_key} - {song_name} (실패 기록 합산: {total_fail}회)")
                        
                        # 첫 번째 항목에 최종 통계 저장
                        first_key, _ = song_list[0]
                        self.attempt_stats[level_key][first_key] = final_stats
                        
                        # 나머지 중복 항목들 제거
                        for key, stats in song_list[1:]:
                            del self.attempt_stats[level_key][key]
                            cleaned_count += 1
                        
                        print(f"중복 정리: {level_key} - {song_name} ({len(song_list)-1}개 제거)")
            
            if cleaned_count > 0:
                self.saveAttemptStats()
                print(f"총 {cleaned_count}개의 중복 항목이 정리되었습니다.")
                
        except Exception as e:
            print(f"중복 정리 중 오류: {e}")
            
    def onClearCheck(self, state):
        if self.current_song and self.current_pattern:
            mode = self.getSelectedMode()
            song_key = f"{self.current_song}_{mode}_{self.current_pattern}"
            # 현재 난이도 키 계산
            level_key = f"{mode}_{self.current_level:.1f}"
            if level_key not in self.attempt_stats:
                self.attempt_stats[level_key] = {}
            if song_key not in self.attempt_stats[level_key]:
                self.attempt_stats[level_key][song_key] = {'success': 0, 'fail': 0}
            if state == Qt.Checked:
                self.attempt_stats[level_key][song_key]['cleared'] = True
            else:
                # 체크 해제 시 cleared 플래그 제거
                self.attempt_stats[level_key][song_key].pop('cleared', None)
            self.saveAttemptStats()

    def onResetClears(self):
        reply = QMessageBox.question(self, '클리어 초기화', 
                                   '모든 클리어 기록을 초기화하시겠습니까?',
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # attempt_stats에서 cleared 플래그 제거
            for level_key, songs in self.attempt_stats.items():
                for song_key, stats in songs.items():
                    if 'cleared' in stats:
                        stats.pop('cleared', None)
            self.saveAttemptStats()
            if self.current_song and self.current_pattern:
                self.clear_checkbox.setChecked(False)
            QMessageBox.information(self, '초기화 완료', 
                                  '모든 클리어 기록이 초기화되었습니다.')

    def updateLevelCombo(self):
        levels = [
            1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3,
            4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3,
            7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3,
            10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3,
            13.1, 13.2, 13.3, 14.1, 14.2, 14.3, 15.1, 15.2, 15.3,
            16.1, 16.2
        ]
        self.level_combo.clear()
        for level in levels:
            self.level_combo.addItem(f"{level:.1f}")
            
    def onStart(self):
        # 시작 버튼을 누를 때 곡 데이터 업데이트
        self.start_btn.setEnabled(False)
        self.start_btn.setText('데이터 업데이트 중...')
        QApplication.processEvents()  # UI 업데이트
        
        # 곡 데이터 업데이트 시도
        update_success = self.updateSongsData()
        
        self.start_btn.setEnabled(True)
        self.start_btn.setText('시작')
        
        if not update_success:
            # 업데이트 실패 시 기존 로컬 데이터 사용
            print("온라인 업데이트 실패, 기존 로컬 데이터 사용")
        
        # 현재 난이도 설정
        self.current_level = float(self.level_combo.currentText())
        # 화면 업데이트 (저장된 진행도 유지)
        self.updateDisplay()
        self.checkAndDisplayFailedLevels()  # 실패한 난이도 표시 업데이트
        self.success_btn.setEnabled(True)
        self.fail_btn.setEnabled(True)
        self.saveLastSettings()  # 시작할 때 현재 설정 저장
        
    def onResetCurrentLevel(self):
        """현재 난이도의 진행도를 초기화합니다."""
        current_mode = self.getSelectedMode()
        reply = QMessageBox.question(self, '현재 난이도 초기화', 
                                   f'{current_mode} 모드 {self.current_level:.1f} 난이도의\n진행도를 초기화하시겠습니까?',
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            level_key = f"{current_mode}_{self.current_level:.1f}"
            
            # 현재 난이도만 초기화
            if level_key in self.shown_songs:
                del self.shown_songs[level_key]
            if level_key in self.failed_songs:
                del self.failed_songs[level_key]
            if level_key in self.result_stats:
                del self.result_stats[level_key]
                self.saveResultStats()
            if level_key in self.attempt_stats:
                del self.attempt_stats[level_key]
                self.saveAttemptStats()
            
            self.saveShownSongs()
            self.updateDisplay()
            self.checkAndDisplayFailedLevels()  # 실패한 난이도 표시 업데이트
            QMessageBox.information(self, '초기화 완료', 
                                  f'{current_mode} 모드 {self.current_level:.1f} 난이도의\n진행도가 초기화되었습니다.')
            
    def onResetAllLevels(self):
        """현재 모드의 모든 난이도 진행도를 초기화합니다."""
        current_mode = self.getSelectedMode()
        reply = QMessageBox.question(self, '전체 모드 초기화', 
                                   f'{current_mode} 모드의 모든 난이도\n진행도를 초기화하시겠습니까?',
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # 현재 모드의 모든 진행도 초기화
            keys_to_remove = []
            for level_key in self.shown_songs.keys():
                if level_key.startswith(f"{current_mode}_"):
                    keys_to_remove.append(level_key)
            
            for key in keys_to_remove:
                del self.shown_songs[key]
            
            # 현재 모드의 실패 기록도 초기화
            failed_keys_to_remove = []
            for level_key in self.failed_songs.keys():
                if level_key.startswith(f"{current_mode}_"):
                    failed_keys_to_remove.append(level_key)
            
            for key in failed_keys_to_remove:
                del self.failed_songs[key]

            # 현재 모드의 성공/실패 통계도 초기화
            stats_keys_to_remove = []
            for level_key in list(self.result_stats.keys()):
                if level_key.startswith(f"{current_mode}_"):
                    stats_keys_to_remove.append(level_key)
            for key in stats_keys_to_remove:
                del self.result_stats[key]
            self.saveResultStats()
            # 현재 모드의 시도 통계도 초기화
            attempt_keys_to_remove = []
            for level_key in list(self.attempt_stats.keys()):
                if level_key.startswith(f"{current_mode}_"):
                    attempt_keys_to_remove.append(level_key)
            for key in attempt_keys_to_remove:
                del self.attempt_stats[key]
            self.saveAttemptStats()
            
            self.saveShownSongs()
            self.updateDisplay()
            self.checkAndDisplayFailedLevels()  # 실패한 난이도 표시 업데이트
            QMessageBox.information(self, '초기화 완료', 
                                  f'{current_mode} 모드의 모든 난이도\n진행도가 초기화되었습니다.')
        
    def getSelectedMode(self):
        try:
            # mode_buttons가 존재하고 비어있지 않은지 확인
            if hasattr(self, 'mode_buttons') and self.mode_buttons:
                for mode, btn in self.mode_buttons.items():
                    if btn.isChecked():
                        return mode
            # 선택된 모드가 없을 경우 기본값 반환
            return '4B'
        except Exception as e:
            print(f"모드 선택 확인 중 오류: {e}")
            return '4B'
        
    def loadSongsData(self):
        """캐시된 곡 데이터를 반환하거나, 필요한 경우 파일에서 새로 로드합니다."""
        current_time = time.time()
        
        # 자동 업데이트 확인
        self.checkForAutoUpdate()
        
        # 캐시가 없거나 만료된 경우
        if self.songs_cache is None or (current_time - self.songs_cache_time) > self.cache_timeout:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                songs_path = os.path.join(script_dir, 'songs.json')
                
                if not os.path.exists(songs_path):
                    print("로컬 곡 데이터가 없습니다. 시작 버튼을 눌러주세요.")
                    return None
                
                with open(songs_path, 'r', encoding='utf-8') as f:
                    self.songs_cache = json.load(f)
                    self.songs_cache_time = current_time
                    print("곡 데이터를 새로 로드했습니다.")
            except Exception as e:
                print(f"곡 데이터 로드 중 오류 발생: {e}")
                return None
                
        return self.songs_cache

    def updateDisplay(self):
        self.level_label.setText(f'현재 난이도: {self.current_level:.1f}')
        
        songs = self.loadSongsData()
        if songs is None:
            self.song_list.setText('곡 데이터를 로드할 수 없습니다')
            return
            
        try:
            mode = self.getSelectedMode()
            matching_songs = []
            total_songs = 0
            cleared_count = 0
            level_key = f"{mode}_{self.current_level:.1f}"
            attempt_level = self.attempt_stats.get(level_key, {})
            
            # 전체 곡 수와 클리어한 곡 수 계산
            for song in songs:
                if mode in song['patterns']:
                    patterns = song['patterns'][mode]
                    for diff_type, info in patterns.items():
                        if isinstance(info, dict) and 'floor' in info:
                            if abs(info['floor'] - self.current_level) < 0.01:
                                total_songs += 1
                                song_key = f"{song['name']}_{mode}_{diff_type}"
                                stats = attempt_level.get(song_key, {})
                                if stats.get('cleared', False):
                                    cleared_count += 1
                                else:
                                    # 클리어하지 않았고 시도 기록도 없는 곡만 후보에 추가 (composer 포함)
                                    if stats.get('success', 0) > 0 or stats.get('fail', 0) > 0:
                                        # 이미 시도한 곡은 후보 목록에서만 제외하고, 진행도 분자는 아래 루프에서 계산
                                        continue
                                    matching_songs.append((
                                        song['name'],
                                        song.get('composer', '?'),
                                        diff_type,
                                        info.get('level', '?')
                                    ))
            
            remaining_songs = total_songs - cleared_count  # 남은 곡 수 계산
            
            # 진행도 표시 (성공 또는 실패 기록이 있는 곡의 개수)
            played_count = 0
            if level_key in self.attempt_stats:
                # attempt_stats에서 성공 또는 실패 기록이 있는 곡 카운트 (cleared는 제외)
                for song_key, stats in self.attempt_stats[level_key].items():
                    if stats.get('cleared', False):
                        continue
                    if stats.get('success', 0) > 0 or stats.get('fail', 0) > 0:
                        played_count += 1
            # played_count는 이미 cleared를 제외한, 실제로 시도한 곡 수이므로 그대로 사용
            self.progress_label.setText(f'진행도: {played_count}/{remaining_songs}')
            # 성공/실패 라벨 업데이트 (곡+패턴별 고유 집계)
            unique_success = 0
            unique_fail = 0
            try:
                for song_key, r in attempt_level.items():
                    s = int(r.get('success', 0))
                    f = int(r.get('fail', 0))
                    if s > 0:
                        unique_success += 1
                    if f > 0 and s == 0:
                        # 한 번이라도 성공했으면 실패만 카운트하지 않음 (중복 방지)
                        unique_fail += 1 if f > 0 and s == 0 else 0
                    elif f > 0 and s == 0:
                        unique_fail += 1
            except Exception:
                pass
            self.sf_label.setText(
                f"<b><span style='color:#2e7d32'>성공: {unique_success}</span></b> / "
                f"<b><span style='color:#d32f2f'>실패: {unique_fail}</span></b>"
            )
            
            if matching_songs:
                # level_key가 없으면 초기화
                if level_key not in self.shown_songs:
                    self.shown_songs[level_key] = set()
                
                # 아직 보지 않은 곡 필터링 (cleared 여부는 위에서 제외됨)
                unplayed_songs = [song for song in matching_songs if (song[0], song[2]) not in self.shown_songs[level_key]]
                
                # 모든 곡을 다 봤을 경우
                if not unplayed_songs:
                    self.song_list.setText('현재 난이도의 모든 곡을 플레이했습니다!')
                    self.clear_checkbox.setEnabled(False)
                    self.current_song = None
                    self.current_pattern = None
                    return
                
                # 랜덤하게 곡 선택
                selected_song = random.choice(unplayed_songs)
                
                # 선택된 곡 정보 저장 (아직 shown_songs에는 추가하지 않음)
                self.current_song = selected_song[0]
                self.current_pattern = selected_song[2]
                
                # 클리어 체크박스 상태 업데이트
                song_key = f"{self.current_song}_{mode}_{self.current_pattern}"
                stats = attempt_level.get(song_key, {})
                self.clear_checkbox.setChecked(bool(stats.get('cleared', False)))
                self.clear_checkbox.setEnabled(True)
                
                # 화면에 선택된 곡 표시 (색상 적용)
                color_map = {
                    "NM": "#FFD600",   # 노랑
                    "HD": "#FF9800",   # 주황
                    "MX": "#F44336",   # 빨강
                    "SC": "#9C27B0"    # 보라
                }
                diff_type = selected_song[2]
                color = color_map.get(diff_type, "#000000")
                level = selected_song[3]
                name = selected_song[0]
                composer = selected_song[1]
                self.song_list.setTextFormat(Qt.RichText)
                self.song_list.setText(
                    f"⭐ {name} - {composer}<br/>"
                    f"<span style='color:{color}; font-weight:bold'>{diff_type}({level})</span>"
                )
                
            else:
                if total_songs > 0:  # 곡이 있지만 모두 클리어한 경우
                    self.song_list.setText('현재 난이도의 모든 곡을 클리어했습니다!')
                else:  # 해당 난이도에 곡이 없는 경우
                    self.song_list.setText('선택한 난이도의 곡이 없습니다')
                self.clear_checkbox.setEnabled(False)
                self.current_song = None
                self.current_pattern = None
                # 성공/실패 라벨 업데이트 (곡이 없거나 모두 클리어한 경우에도, 고유 집계)
                unique_success = 0
                unique_fail = 0
                try:
                    attempt_level = self.attempt_stats.get(level_key, {})
                    for song_key, r in attempt_level.items():
                        s = int(r.get('success', 0))
                        f = int(r.get('fail', 0))
                        if s > 0:
                            unique_success += 1
                        if f > 0 and s == 0:
                            unique_fail += 1
                except Exception:
                    pass
                self.sf_label.setText(
                    f"<b><span style='color:#2e7d32'>성공: {unique_success}</span></b> / "
                    f"<b><span style='color:#d32f2f'>실패: {unique_fail}</span></b>"
                )
                
        except Exception as e:
            self.song_list.setText(f'오류 발생: {str(e)}')
            
    def onSuccess(self):
        # 현재 곡이 있으면 항상 진행도에 추가 (중복 체크 없음)
        if self.current_song and self.current_pattern:
            level_key = f"{self.getSelectedMode()}_{self.current_level:.1f}"
            if level_key not in self.shown_songs:
                self.shown_songs[level_key] = set()
                
            # 항상 shown_songs에 추가 (중복 가능)
            self.shown_songs[level_key].add((self.current_song, self.current_pattern))
            self.saveShownSongs()  # 진행도 저장
            # 성공 카운트 증가
            self._incrementResult(level_key, 'success')
            # 곡+패턴 시도 카운트 증가
            self._incrementAttempt(self.getSelectedMode(), self.current_level, self.current_song, self.current_pattern, 'success')
        
        # 난이도 상승 (진행도 꽉 찬 난이도는 건너뜀)
        self.current_level = self._find_next_level_skipping_full(direction='up', fallback=self.current_level)
        
        # 설정 저장 (난이도 변경 후)
        self.saveLastSettings()
        self.updateDisplay()
        self.checkAndDisplayFailedLevels()  # 실패한 난이도 표시 업데이트
        
    def onFail(self):
        # 현재 곡이 있으면 항상 진행도에 추가 (중복 체크 없음)
        if self.current_song and self.current_pattern:
            level_key = f"{self.getSelectedMode()}_{self.current_level:.1f}"
            if level_key not in self.shown_songs:
                self.shown_songs[level_key] = set()
                
            # 항상 shown_songs에 추가 (중복 가능)
            self.shown_songs[level_key].add((self.current_song, self.current_pattern))
            self.saveShownSongs()  # 진행도 저장
            
            # 실패 기록 추가
            if level_key not in self.failed_songs:
                self.failed_songs[level_key] = set()
            self.failed_songs[level_key].add((self.current_song, self.current_pattern))
            # 실패 카운트 증가
            self._incrementResult(level_key, 'fail')
            # 곡+패턴 시도 카운트 증가
            self._incrementAttempt(self.getSelectedMode(), self.current_level, self.current_song, self.current_pattern, 'fail')
            
        
        # 난이도 하락 (진행도 꽉 찬 난이도는 건너뜀)
        self.current_level = self._find_next_level_skipping_full(direction='down', fallback=self.current_level)
        
        # 설정 저장 (난이도 변경 후)
        self.saveLastSettings()
        self.updateDisplay()
        self.checkAndDisplayFailedLevels()  # 실패한 난이도 표시 업데이트



    def _is_level_progress_full(self, mode, level_value):
        """해당 모드/난이도의 진행도가 꽉 찼는지 여부를 반환합니다.
        - 기준: 아직 클리어하지 않은 후보 곡(이름, 패턴)의 집합이
                shown_songs[level_key]에 모두 포함되어 있으면 꽉 참.
        - 후보가 전혀 없을 때(곡이 없거나 모두 클리어됨)도 꽉 찬 것으로 간주합니다.
        """
        try:
            songs = self.loadSongsData()
            if songs is None:
                return False
            level_key = f"{mode}_{level_value:.1f}"
            attempt_level = self.attempt_stats.get(level_key, {})
            candidate_set = set()
            for song in songs:
                if mode in song.get('patterns', {}):
                    patterns = song['patterns'][mode]
                    for diff_type, info in patterns.items():
                        if isinstance(info, dict) and 'floor' in info:
                            if abs(info['floor'] - level_value) < 0.01:
                                song_key = f"{song['name']}_{mode}_{diff_type}"
                                stats = attempt_level.get(song_key, {})
                                if not stats.get('cleared', False):
                                    candidate_set.add((song['name'], diff_type))
            shown_set = self.shown_songs.get(level_key, set())
            # 후보가 없거나, 후보가 모두 shown에 포함되면 꽉 참
            return (not candidate_set) or candidate_set.issubset(shown_set)
        except Exception:
            return False

    def _find_next_level_skipping_full(self, direction='up', fallback=None):
        """위/아래 방향으로 이동하되 진행도 꽉 찬 난이도를 건너뜁니다.
        - direction: 'up'이면 더 높은 난이도, 'down'이면 더 낮은 난이도.
        - fallback: 적절한 난이도를 찾지 못했을 때 유지할 값.
        """
        try:
            levels = [float(self.level_combo.itemText(i)) for i in range(self.level_combo.count())]
            mode = self.getSelectedMode()
            if direction == 'up':
                for level in levels:
                    if level > self.current_level:
                        if not self._is_level_progress_full(mode, level):
                            return level
                # 위로 더 이상 없거나 모두 꽉 찼을 때는 마지막 가능한 값 유지
                return fallback if fallback is not None else self.current_level
            else:
                for level in reversed(levels):
                    if level < self.current_level:
                        if not self._is_level_progress_full(mode, level):
                            return level
                # 아래로 더 이상 없거나 모두 꽉 찼을 때는 현재 값 유지
                return fallback if fallback is not None else self.current_level
        except Exception:
            return fallback if fallback is not None else self.current_level
    
    def closeEvent(self, event):
        """프로그램 종료 시 현재 설정과 진행상황을 저장합니다."""
        self.saveLastSettings()
        self.saveShownSongs()  # 진행상황 저장
        event.accept()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        window = DifficultyWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {e}")
        sys.exit(1)
